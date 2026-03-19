from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import common


class TestMatomoAnalytics(common.SingleTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.instance = cls.env["matomo.instance"].create(
            {
                "name": "Main Site",
                "base_url": "https://analytics.example.com",
                "site_id": 7,
                "api_token": "secret-token",
                "sync_window_days": 2,
                "page_limit": 5,
            }
        )

    @staticmethod
    def _fake_do_post(self, payload):
        method = payload["method"]
        if method == "API.getMatomoVersion":
            return "5.1.0"
        if method == "SitesManager.getSiteFromId":
            return {"idsite": payload.get("idSite")}
        if method == "Goals.get":
            return {"nb_conversions": 3, "conversion_rate": 20.0, "revenue": 25.0}
        if method == "API.getProcessedReport":
            return {
                "reportData": [
                    {
                        "label": "Donation",
                        "nb_conversions": 2,
                        "conversion_rate": 10.0,
                        "revenue": 25.0,
                    },
                    {
                        "label": "Signup",
                        "nb_conversions": 1,
                        "conversion_rate": 5.0,
                        "revenue": 0.0,
                    },
                ]
            }
        if method == "API.getBulkRequest":
            return [
                {
                    "nb_visitors": 10,
                    "nb_visits": 15,
                    "bounce_rate": 40.0,
                    "avg_time_on_site": 120,
                },
                [
                    {"label": "Direct Entry", "nb_visits": 9, "nb_visitors": 8},
                    {"label": "Search", "nb_visits": 6, "nb_visitors": 5},
                ],
                [
                    {"label": "/home", "nb_visits": 10, "nb_hits": 20},
                    {"label": "/about", "nb_visits": 5, "nb_hits": 8},
                ],
                [
                    {"label": "/home", "entry_nb_visits": 8, "bounce_rate": 25.0},
                ],
                [
                    {"label": "/checkout", "exit_nb_visits": 7, "exit_rate": 70.0},
                ],
                [
                    {
                        "label": "Netherlands",
                        "code": "NL",
                        "nb_visits": 6,
                        "nb_visitors": 5,
                    }
                ],
                [
                    {
                        "label": "google.com",
                        "type": "search",
                        "nb_visits": 6,
                        "nb_visitors": 5,
                    }
                ],
            ]
        raise AssertionError("Unexpected Matomo method: %s" % method)

    @staticmethod
    def _fake_do_post_goals_unavailable(self, payload):
        if payload["method"] in ("Goals.get", "API.getProcessedReport"):
            raise UserError("Goals are not enabled for this site.")
        return TestMatomoAnalytics._fake_do_post(self, payload)

    @staticmethod
    def _fake_do_post_missing_bulk_sections(self, payload):
        if payload["method"] == "API.getBulkRequest":
            return [
                {
                    "nb_visitors": 10,
                    "nb_visits": 15,
                    "bounce_rate": 40.0,
                    "avg_time_on_site": 120,
                },
                [
                    {"label": "Direct Entry", "nb_visits": 9, "nb_visitors": 8},
                    {"label": "Search", "nb_visits": 6, "nb_visitors": 5},
                ],
            ]
        return TestMatomoAnalytics._fake_do_post(self, payload)

    def test_connection_action_marks_instance_tested(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post,
        ):
            action = self.instance.action_test_connection()

        self.assertEqual(action["params"]["type"], "success")
        self.assertTrue(self.instance.last_tested_on)

    def test_sync_creates_metrics_and_success_log(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post,
        ):
            action = self.instance.action_sync_now()

        self.assertEqual(action["params"]["type"], "success")
        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(log.state, "success")
        self.assertEqual(log.warning_count, 0)
        self.assertEqual(log.daily_records, 2)
        self.assertEqual(log.goal_records, 4)
        self.assertEqual(
            self.env["matomo.daily.metric"].search_count(
                [("instance_id", "=", self.instance.id)]
            ),
            2,
        )
        self.assertEqual(
            self.env["matomo.goal.metric"].search_count(
                [("instance_id", "=", self.instance.id)]
            ),
            4,
        )
        self.assertEqual(self.instance.last_sync_state, "success")

    def test_sync_marks_partial_when_goals_are_unavailable(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goals_unavailable,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.daily_records, 2)
        self.assertEqual(log.goal_records, 0)
        self.assertEqual(log.warning_count, 4)
        self.assertIn("Goal summary unavailable", log.warning_details)
        self.assertEqual(self.instance.last_sync_state, "partial")

    def test_sync_marks_partial_when_bulk_sections_are_missing(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_missing_bulk_sections,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.daily_records, 2)
        self.assertEqual(log.country_records, 0)
        self.assertEqual(log.referrer_records, 0)
        self.assertGreater(log.warning_count, 0)
        self.assertIn(
            "Top pages report missing from bulk response", log.warning_details
        )

    def test_sync_marks_partial_when_a_later_day_fails(self):
        bulk_calls = {"count": 0}

        def side_effect(mock_self, payload):
            if payload["method"] == "API.getBulkRequest":
                bulk_calls["count"] += 1
                if bulk_calls["count"] == 2:
                    raise UserError("Matomo bulk request failed on the second day.")
            return self._fake_do_post(mock_self, payload)

        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=side_effect,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.imported_days, 1)
        self.assertEqual(log.daily_records, 1)
        self.assertIn("Sync stopped after importing 1 days", log.message)

    def test_sync_marks_failed_when_no_day_can_be_imported(self):
        def side_effect(_mock_self, payload):
            if payload["method"] == "API.getBulkRequest":
                raise UserError("Matomo bulk request failed immediately.")
            return self._fake_do_post(_mock_self, payload)

        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=side_effect,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "danger")
        self.assertEqual(log.state, "failed")
        self.assertEqual(log.imported_days, 0)
        self.assertEqual(log.imported_records, 0)
        self.assertIn("failed immediately", log.message)

    def test_dashboard_aggregates_stored_metrics(self):
        today = fields.Date.context_today(self.instance)
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post,
        ):
            self.instance.action_sync_now()

        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": self.instance.id,
                "date_from": today - timedelta(days=1),
                "date_to": today,
                "comparison_enabled": True,
                "compare_date_from": today - timedelta(days=1),
                "compare_date_to": today,
            }
        )

        self.assertEqual(wizard.total_visitors, 20)
        self.assertEqual(wizard.total_sessions, 30)
        self.assertEqual(wizard.total_conversions, 6.0)
        self.assertEqual(wizard.top_channel, "Direct Entry")
        self.assertEqual(wizard.compare_sessions, 30)
        self.assertEqual(wizard.sessions_delta, 0.0)

    def test_dashboard_weights_bounce_rate_by_sessions(self):
        weighted_instance = self.env["matomo.instance"].create(
            {
                "name": "Weighted Bounce Site",
                "base_url": "https://analytics.example.com",
                "site_id": 99,
                "api_token": "secret-token",
                "sync_window_days": 2,
                "page_limit": 5,
            }
        )
        today = fields.Date.context_today(weighted_instance)
        daily_metric_model = self.env["matomo.daily.metric"]
        daily_metric_model.create(
            [
                {
                    "company_id": weighted_instance.company_id.id,
                    "instance_id": weighted_instance.id,
                    "date": today - timedelta(days=10),
                    "visitors": 80,
                    "sessions": 100,
                    "conversions": 2.0,
                    "bounce_rate": 10.0,
                },
                {
                    "company_id": weighted_instance.company_id.id,
                    "instance_id": weighted_instance.id,
                    "date": today - timedelta(days=9),
                    "visitors": 1,
                    "sessions": 1,
                    "conversions": 0.0,
                    "bounce_rate": 90.0,
                },
                {
                    "company_id": weighted_instance.company_id.id,
                    "instance_id": weighted_instance.id,
                    "date": today - timedelta(days=8),
                    "visitors": 5,
                    "sessions": 5,
                    "conversions": 1.0,
                    "bounce_rate": 50.0,
                },
                {
                    "company_id": weighted_instance.company_id.id,
                    "instance_id": weighted_instance.id,
                    "date": today - timedelta(days=7),
                    "visitors": 40,
                    "sessions": 45,
                    "conversions": 3.0,
                    "bounce_rate": 10.0,
                },
            ]
        )

        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": weighted_instance.id,
                "date_from": today - timedelta(days=10),
                "date_to": today - timedelta(days=9),
                "comparison_enabled": True,
                "compare_date_from": today - timedelta(days=8),
                "compare_date_to": today - timedelta(days=7),
            }
        )

        self.assertAlmostEqual(wizard.bounce_rate, (1000.0 + 90.0) / 101.0, places=4)
        self.assertAlmostEqual(
            wizard.compare_bounce_rate, (250.0 + 450.0) / 50.0, places=4
        )
