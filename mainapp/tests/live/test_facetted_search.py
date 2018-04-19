import time
from datetime import date
from unittest import mock
from urllib import parse

from django.test import override_settings
from selenium.webdriver.common.keys import Keys

from mainapp.models import Person
from mainapp.tests.live.chromedriver_test_case import ChromeDriverTestCase
from mainapp.tests.live.helper import MockMainappSearch, MockMainappSearchEndlessScroll, mock_search_autocomplete
from meine_stadt_transparent import settings


class FacettedSearchTest(ChromeDriverTestCase):
    fixtures = ['initdata.json']

    def get_search_string_from_url(self):
        return parse.unquote(self.browser.url.split("/")[-2])

    def assert_query_equals(self):
        return parse.unquote(self.browser.url.split("/")[-2])

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.views.Search.execute", new=mock_search_autocomplete)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_landing_page_redirect(self):
        """ There was a case where the redirect would lead to the wrong page """
        self.visit('/')
        self.browser.fill("search-query", "word")
        self.browser.find_by_name("search-query").first._element.send_keys(Keys.ENTER)
        self.assertEqual("word", self.get_search_string_from_url())

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_word(self):
        self.visit('/search/query/word/')
        self.assertTrue(self.browser.is_text_present("Highlight"))

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_document_type(self):
        self.visit('/search/query/word/')
        self.assertTextIsPresent("Document Type")
        self.assertTextIsNotPresent("Meeting")
        self.browser.click_link_by_id("documentTypeButton")
        self.assertTextIsPresent("Meeting")
        self.browser.check("document-type[person]")
        self.browser.check("document-type[file]")
        self.browser.check("document-type[meeting]")
        self.assertEqual("document-type:file,meeting,person word", self.get_search_string_from_url())
        self.browser.uncheck("document-type[meeting]")
        self.assertEqual("document-type:file,person word", self.get_search_string_from_url())
        self.click_by_css("#filter-document-type-list .remove-filter")
        self.assertEqual("word", self.get_search_string_from_url())

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_time_range(self):
        self.visit('/search/query/word/')
        self.click_by_id("timeRangeButton")
        self.click_by_text("This year")

        first_day = date(date.today().year, 1, 1)
        last_day = date(date.today().year, 12, 31)
        self.assertEqual("after:{} before:{} word".format(first_day, last_day), self.get_search_string_from_url())

        self.click_by_id("timeRangeButton")
        self.click_by_css(".daterangepicker .remove-filter")
        self.assertEqual("word", self.get_search_string_from_url())

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_person_filter(self):
        self.visit('/search/query/word/')
        self.click_by_id("personButton")
        self.click_by_text("Frank Underwood")

        self.assertEqual("person:1 word", self.get_search_string_from_url())

        self.click_by_id("personButton")
        self.browser.find_by_css(".show .remove-filter").first.click()

        self.assertEqual("word", self.get_search_string_from_url())

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_sorting(self):
        self.visit('/search/query/word/')
        self.click_by_id("btnSortDropdown")
        self.click_by_text("Newest first")

        self.assertEqual("sort:date_newest word", self.get_search_string_from_url())

        self.click_by_id("btnSortDropdown")
        self.click_by_text("Relevance")

        self.assertEqual("word", self.get_search_string_from_url())

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_dropdown_filter(self):
        self.visit('/search/query/word/')
        self.click_by_id("personButton")
        count = len(self.browser.find_by_css("[data-filter-key='person'] .filter-item"))
        org = settings.SITE_DEFAULT_ORGANIZATION
        persons = Person.objects.filter(organizationmembership__organization=org).distinct().count()
        self.assertEqual(count, persons)
        self.browser.fill("filter-person", "Frank")
        count = len(self.browser.find_by_css("[data-filter-key='person'] .filter-item"))
        self.assertEqual(count, 1)

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearch.execute)
    def test_dropdown_filter_preseted(self):
        self.visit('/search/query/organization:1 word/')
        self.click_by_id("organizationButton")
        self.assertTextIsPresent("Cancel Selection")
        self.click_by_css('[data-id="2"]')
        self.assertEqual(self.get_search_string_from_url(), "organization:2 word")
        self.click_by_id("organizationButton")
        self.click_by_css("#filter-organization-list .remove-filter")
        self.assertEqual(self.get_search_string_from_url(), "word")

    @override_settings(USE_ELASTICSEARCH=True)
    @mock.patch("mainapp.functions.search_tools.MainappSearch.execute", new=MockMainappSearchEndlessScroll.execute)
    def test_endless_scroll(self):
        self.visit('/search/query/word/')

        single_length = settings.SEARCH_PAGINATION_LENGTH
        self.assertEqual(single_length, len(self.browser.find_by_css(".results-list > li")))
        numbers = [int(i.text) for i in self.browser.find_by_css(".results-list > li .lead")]
        numbers.sort()
        self.assertEqual(numbers, list(range(0, single_length)))

        self.click_by_id("start-endless-scroll")

        # semi-busy waiting
        # (it does work without wating on my machine, but I won't risk having any timing based test failures)
        while single_length == len(self.browser.find_by_css(".results-list > li")):
            time.sleep(0.01)

        self.assertEqual(single_length * 2, len(self.browser.find_by_css(".results-list > li")))
        numbers = [int(i.text) for i in self.browser.find_by_css(".results-list > li .lead")]
        numbers.sort()
        self.assertEqual(numbers, list(range(0, single_length * 2)))
