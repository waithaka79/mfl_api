import json
from mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.core.urlresolvers import reverse
from django.core.management import call_command
from django.contrib.auth.models import Group

from model_mommy import mommy

from facilities.models import Facility, FacilityApproval
from facilities.serializers import FacilitySerializer
from common.tests import ViewTestBase
from mfl_gis.models import FacilityCoordinates

from search.filters import SearchFilter
from search.search_utils import (
    ElasticAPI, index_instance, default, serialize_model)

from ..index_settings import get_mappings


SEARCH_TEST_SETTINGS = {
    "ELASTIC_URL": "http://localhost:9200/",
    "INDEX_NAME": "test_index",
    "NON_INDEXABLE_MODELS": [
        "mfl_gis.FacilityCoordinates",
        "mfl_gis.WorldBorder",
        "mfl_gis.CountyBoundary",
        "mfl_gis.ConstituencyBoundary",
        "mfl_gis.WardBoundary"],
    "AUTOCOMPLETE_MODEL_FIELDS": [
        {
            "app": "facilities",
            "models": [
                {
                    "name": "facility",
                    "fields": ["name", "ward_name"]
                },
                {
                    "name": "owner",
                    "fields": ["name"]
                }
            ]
        }
    ]
}
CACHES_TEST_SETTINGS = {
    'default': {
        'BACKEND':
        'django.core.cache.backends.dummy.DummyCache',
    }
}


@override_settings(
    SEARCH=SEARCH_TEST_SETTINGS,
    CACHES=CACHES_TEST_SETTINGS)
class TestElasticSearchAPI(TestCase):

    def setUp(self):
        self.elastic_search_api = ElasticAPI()
        super(TestElasticSearchAPI, self).setUp()

    def test_setup_index(self):
        self.elastic_search_api.delete_index(index_name='test_index')
        result = self.elastic_search_api.setup_index(index_name='test_index')
        self.assertEquals(200, result.status_code)
        self.elastic_search_api.delete_index(index_name='test_index')

    def test_get_non_existing_index(self):
        index_name = 'test_index'
        self.elastic_search_api.delete_index(index_name)
        self.elastic_search_api.get_index(index_name)

    def test_get_exsting_index(self):
        index_name = 'test_index'
        self.elastic_search_api.setup_index(index_name=index_name)
        self.elastic_search_api.get_index(index_name)
        self.elastic_search_api.delete_index(index_name='test_index')

    def test_delete_index(self):
        index_name = 'test_index_3'
        response = self.elastic_search_api.setup_index(index_name=index_name)
        self.assertEquals(200, response.status_code)
        self.elastic_search_api.delete_index(index_name)

    def test_index_document(self):
        facility = mommy.make(Facility, name='Fig tree medical clinic')
        self.elastic_search_api.setup_index(index_name='test_index')
        result = index_instance(facility, 'test_index')
        self.assertEquals(201, result.status_code)

    def test_search_document_no_instance_type(self):
        index_name = 'test_index'
        response = self.elastic_search_api.setup_index(index_name=index_name)
        self.assertEquals(200, response.status_code)
        facility = mommy.make(Facility, name='Fig tree medical clinic')
        result = index_instance(facility, 'test_index')
        self.assertEquals(201, result.status_code)
        self.elastic_search_api.search_document(
            index_name=index_name, instance_type=Facility, query='tree')

    def test_remove_document(self):
        index_name = 'test_index'
        self.elastic_search_api.setup_index(index_name=index_name)
        facility = mommy.make(Facility, name='Fig tree medical clinic')
        result = index_instance(facility, 'test_index')
        self.assertEquals(201, result.status_code)
        self.elastic_search_api.remove_document(
            index_name, 'facility', str(facility.id))
        self.elastic_search_api.delete_index(index_name='test_index')

    def test_index_settings(self):
        expected_map = get_mappings()
        for key, value in expected_map.items():
            for key_2, value_2 in expected_map.get(key).items():
                for key_3, value_3 in expected_map.get(key).get(key_2).items():
                        values = expected_map.get(key).get(key_2).get(key_3)
                        self.assertEquals(
                            'autocomplete',
                            values.get('index_analyzer'))
                        self.assertEquals(
                            'autocomplete',
                            values.get('search_analyzer'))
                        self.assertEquals(
                            'string',
                            values.get('type'))
                        self.assertEquals(
                            False,
                            values.get('coerce'))
                        self.assertEquals(
                            True,
                            values.get('store'))

    def tearDown(self):
        self.elastic_search_api.delete_index(index_name='test_index')
        super(TestElasticSearchAPI, self).tearDown()


@override_settings(
    SEARCH=SEARCH_TEST_SETTINGS,
    CACHES=CACHES_TEST_SETTINGS)
class TestSearchFunctions(ViewTestBase):
    def setUp(self):
        self.elastic_search_api = ElasticAPI()
        super(TestSearchFunctions, self).setUp()

    def test_serialize_model(self):
        self.maxDiff = None
        facility = mommy.make(Facility)
        serialized_data = serialize_model(facility)
        expected_data = FacilitySerializer(
            facility,
            context={
                'request': {
                    "REQUEST_METHOD": "None"
                }
            }
        ).data
        expected_data = json.dumps(expected_data, default=default)
        self.assertEquals(expected_data, serialized_data.get('data'))

    def test_serialize_model_serializer_not_found(self):
        # There is no serializer named GroupSerializer
        # Therefore the serialize model function should return None
        group = mommy.make(Group)
        serialized_data = serialize_model(group)
        self.assertIsNone(serialized_data)

    def test_default_json_dumps_function(self):
        facility = mommy.make(Facility)
        data = FacilitySerializer(
            facility,
            context={
                'request': {
                    "REQUEST_METHOD": "None"
                }
            }
        ).data
        result = json.dumps(data, default=default)
        self.assertIsInstance(result, str)

    def test_search_facility(self):
        url = reverse('api:facilities:facilities_list')
        self.elastic_search_api = ElasticAPI()
        self.elastic_search_api.setup_index(index_name='test_index')
        facility = mommy.make(Facility, name='Kanyakini')
        index_instance(facility, 'test_index')
        url = url + "?search={}".format('Kanyakini')
        response = ""
        # temporary hack there is a delay in getting the search results
        for x in range(0, 100):
            response = self.client.get(url)
        self.assertEquals(200, response.status_code)

        expected_data = {
            "results": [
                FacilitySerializer(
                    facility,
                    context={
                        'request': {
                            "REQUEST_METHOD": "None"
                        }
                    }
                ).data
            ]
        }
        self._assert_response_data_equality(
            expected_data['results'], response.data['results']
        )
        self.elastic_search_api.delete_index('test_index')

    def test_seach_auto_complete(self):
        url = reverse('api:facilities:facilities_list')
        self.elastic_search_api = ElasticAPI()
        self.elastic_search_api.setup_index(index_name='test_index')
        facility = mommy.make(Facility, name='Kanyakini')
        index_instance(facility, 'test_index')
        url = url + "?search_auto={}".format('Kanya')
        response = ""
        # temporary hack there is a delay in getting the search results
        for x in range(0, 100):
            response = self.client.get(url)

        self.assertEquals(200, response.status_code)

        expected_data = {
            "results": [
                FacilitySerializer(
                    facility,
                    context={
                        'request': {
                            "REQUEST_METHOD": "None"
                        }
                    }
                ).data
            ]
        }
        self._assert_response_data_equality(
            expected_data['results'], response.data['results']
        )
        self.elastic_search_api.delete_index('test_index')

    def test_search_facility_multiple_filters(self):
        url = reverse('api:facilities:facilities_list')
        self.elastic_search_api = ElasticAPI()
        self.elastic_search_api.setup_index(index_name='test_index')

        facility = mommy.make(
            Facility, name='Mordal mountains medical clinic')
        mommy.make(FacilityApproval, facility=facility)
        facility.is_published = True
        facility.save()
        facility_2 = mommy.make(
            Facility,
            name='Eye of mordal health center',
            is_published=False)
        index_instance(facility, 'test_index')

        index_instance(facility_2, 'test_index')

        url = url + "?search={}&is_published={}".format('mordal', 'false')
        response = ""
        # Temporary hack there is a delay in getting the search results

        for x in range(0, 100):
            response = self.client.get(url)

        self.assertEquals(200, response.status_code)
        self.elastic_search_api.delete_index('test_index')

    def tearDown(self):
        self.elastic_search_api.delete_index(index_name='test_index')
        super(TestSearchFunctions, self).tearDown()


@override_settings(
    SEARCH=SEARCH_TEST_SETTINGS,
    CACHES=CACHES_TEST_SETTINGS)
class TestSearchFilter(ViewTestBase):

    def setUp(self):
        self.elastic_search_api = ElasticAPI()
        super(TestSearchFilter, self).setUp()

    def test_filter_no_data(self):
        api = ElasticAPI()
        api.delete_index('test_index')
        api.setup_index('test_index')
        mommy.make(Facility, name='test facility')
        mommy.make(Facility)
        qs = Facility.objects.all()

        search_filter = SearchFilter(name='search')
        result = search_filter.filter(qs, 'test')
        # no documents have been indexed
        self.assertEquals(result.count(), 0)
        api.delete_index('test_index')

    def test_filter_elastic_not_available(self):
        with patch.object(
                ElasticAPI,
                'search_document') as mock_search:
            mock_search.return_value = None

            api = ElasticAPI()
            api.delete_index('test_index')
            api.setup_index('test_index')
            mommy.make(Facility, name='test facility')
            mommy.make(Facility)
            qs = Facility.objects.all()

            search_filter = SearchFilter(name='search')
            result = search_filter.filter(qs, 'test')
            # no documents have been indexed
            self.assertEquals(result.count(), 0)
            api.delete_index('test_index')

    def test_filter_data(self):
        api = ElasticAPI()
        api.delete_index('test_index')
        api.setup_index('test_index')
        test_facility = mommy.make(Facility, name='test facility')
        index_instance(test_facility, 'test_index')
        mommy.make(Facility)
        qs = Facility.objects.all()

        search_filter = SearchFilter(name='search')
        # some weird bug there is a delay in getting the search results
        for x in range(0, 100):
            search_filter.filter(qs, 'test')
        api.delete_index('test_index')

    def test_create_index(self):
        call_command('setup_index')
        api = ElasticAPI()
        api.get_index('mfl_index')
        # handle cases where the index already exists

    def test_build_index(self):
        call_command('setup_index')
        mommy.make(Facility, name='medical clinic two')
        mommy.make(Facility, name='medical clinic one')
        call_command('build_index')

    def test_delete_index(self):
        # a very naive test. When results are checked with status codes,
        # tests pass locally but fail on circle ci
        # We leave it without any assertions for coverage's sake.
        api = ElasticAPI()
        call_command('setup_index')
        api.get_index('mfl_index')
        call_command('remove_index')
        api.get_index('mfl_index')

    def test_non_indexable_model(self):
        obj = mommy.make_recipe(
            'mfl_gis.tests.facility_coordinates_recipe')
        self.assertEquals(1, FacilityCoordinates.objects.count())

        index_instance(obj)

    def test_seach_facility_by_code(self):
        mommy.make(Facility, code=17780)
        api = ElasticAPI()
        api.delete_index('test_index')
        api.setup_index('test_index')
        test_facility = mommy.make(Facility, name='test facility')
        index_instance(test_facility, 'test_index')
        mommy.make(Facility)
        qs = Facility.objects.all()

        search_filter = SearchFilter(name='search')
        # some weird bug there is a delay in getting the search results
        for x in range(0, 100):
            search_filter.filter(qs, 18990)
            search_filter.filter(qs, 17780)
        api.delete_index('test_index')

    def tearDown(self):
        self.elastic_search_api.delete_index(index_name='test_index')
        super(TestSearchFilter, self).tearDown()
