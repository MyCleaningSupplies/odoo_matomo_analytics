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
        if method == "Goals.getGoals":
            return []
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
        if payload["method"] in ("Goals.get", "API.getProcessedReport", "Goals.getGoals"):
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

    @staticmethod
    def _fake_do_post_goal_payloads_empty(self, payload):
        if payload["method"] == "Goals.get":
            return {}
        if payload["method"] == "API.getProcessedReport":
            return {"reportData": []}
        return TestMatomoAnalytics._fake_do_post(self, payload)

    @staticmethod
    def _fake_do_post_goal_breakdown_malformed(self, payload):
        if payload["method"] == "API.getProcessedReport":
            return {"reportData": "bad-goal-payload"}
        return TestMatomoAnalytics._fake_do_post(self, payload)

    @staticmethod
    def _fake_do_post_goal_summary_malformed(self, payload):
        if payload["method"] == "Goals.get":
            return "bad-summary"
        return TestMatomoAnalytics._fake_do_post(self, payload)

    @staticmethod
    def _fake_do_post_summary_as_list(self, payload):
        if payload["method"] == "API.getBulkRequest":
            response = TestMatomoAnalytics._fake_do_post(self, payload)
            response[0] = [response[0]]
            return response
        return TestMatomoAnalytics._fake_do_post(self, payload)

    @staticmethod
    def _fake_do_post_zero_goal_conversions(self, payload):
        if payload["method"] == "Goals.get":
            return {"nb_conversions": 0, "conversion_rate": 0.0, "revenue": 0.0}
        if payload["method"] == "API.getProcessedReport":
            return {"reportData": []}
        return TestMatomoAnalytics._fake_do_post(self, payload)

    @staticmethod
    def _fake_do_post_goal_processed_report_unavailable(self, payload):
        if payload["method"] == "API.getProcessedReport":
            raise UserError(
                "Requested report Goals.get for Website id=19 not found in the list of available reports."
            )
        if payload["method"] == "Goals.getGoals":
            return [
                {"idgoal": 1, "name": "Signup"},
                {"idgoal": 2, "name": "Donation"},
            ]
        if payload["method"] == "Goals.get":
            id_goal = payload.get("idGoal")
            if id_goal == "all":
                return {"nb_conversions": 3, "conversion_rate": 20.0, "revenue": 25.0}
            if id_goal == 1:
                return {"nb_conversions": 1, "conversion_rate": 5.0, "revenue": 0.0}
            if id_goal == 2:
                return {"nb_conversions": 2, "conversion_rate": 10.0, "revenue": 25.0}
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
        self.assertEqual(self.instance.latest_sync_log_id.id, log.id)
        self.assertEqual(self.instance.last_sync_warning_count, 4)
        self.assertIn(
            "Goal summary unavailable", self.instance.last_sync_warning_summary
        )

    def test_sync_marks_partial_when_goal_payloads_are_empty(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goal_payloads_empty,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.goal_records, 0)
        self.assertEqual(log.warning_count, 2)
        self.assertIn("Goal summary report was empty.", log.warning_details)

    def test_sync_falls_back_to_goal_summary_when_breakdown_is_malformed(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goal_breakdown_malformed,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.goal_records, 2)
        self.assertIn(
            "Goal breakdown report had unexpected row payload type str.",
            log.warning_details,
        )
        goal_metrics = self.env["matomo.goal.metric"].search(
            [("instance_id", "=", self.instance.id)]
        )
        self.assertEqual(len(goal_metrics), 2)
        self.assertEqual(set(goal_metrics.mapped("goal_name")), {"All Goals"})

    def test_sync_marks_partial_when_goal_summary_is_malformed(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goal_summary_malformed,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.goal_records, 4)
        self.assertIn(
            "Goal summary report had unexpected payload type str.",
            log.warning_details,
        )
        self.assertEqual(
            sum(
                self.env["matomo.daily.metric"]
                .search([("instance_id", "=", self.instance.id)])
                .mapped("conversions")
            ),
            6.0,
        )

    def test_sync_falls_back_when_goal_processed_report_is_unavailable(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goal_processed_report_unavailable,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "success")
        self.assertEqual(log.state, "success")
        self.assertEqual(log.warning_count, 0)
        self.assertEqual(log.goal_records, 4)
        goal_metrics = self.env["matomo.goal.metric"].search(
            [("instance_id", "=", self.instance.id)]
        )
        self.assertEqual(set(goal_metrics.mapped("goal_name")), {"Signup", "Donation"})

    def test_sync_accepts_summary_report_as_single_row_list(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_summary_as_list,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "success")
        self.assertEqual(log.state, "success")
        self.assertEqual(log.warning_count, 0)

    def test_sync_allows_empty_goal_breakdown_when_summary_has_no_conversions(self):
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_zero_goal_conversions,
        ):
            action = self.instance.action_sync_now()

        log = self.env["matomo.sync.log"].search(
            [("instance_id", "=", self.instance.id)], limit=1
        )
        self.assertEqual(action["params"]["type"], "success")
        self.assertEqual(log.state, "success")
        self.assertEqual(log.warning_count, 0)
        self.assertEqual(log.goal_records, 0)

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
                "comparison_mode": "custom",
                "compare_date_from": today - timedelta(days=1),
                "compare_date_to": today,
            }
        )

        self.assertEqual(wizard.total_visitors, 20)
        self.assertEqual(wizard.total_sessions, 30)
        self.assertEqual(wizard.total_conversions, 6.0)
        self.assertEqual(wizard.conversion_rate, 20.0)
        self.assertEqual(wizard.top_channel, "Direct Entry")
        self.assertEqual(wizard.compare_sessions, 30)
        self.assertEqual(wizard.sessions_delta, 0.0)
        self.assertIn("Direct Entry", wizard.top_channels_summary)
        self.assertIn("/home", wizard.top_pages_summary)
        self.assertIn("Donation", wizard.top_goals_summary)

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
                "date_from": today - timedelta(days=8),
                "date_to": today - timedelta(days=7),
                "comparison_enabled": True,
            }
        )

        self.assertAlmostEqual(wizard.bounce_rate, (250.0 + 450.0) / 50.0, places=4)
        self.assertAlmostEqual(
            wizard.compare_bounce_rate, (1000.0 + 90.0) / 101.0, places=4
        )
        self.assertIn("Previous period", wizard.compare_range_label)

    def test_dashboard_surfaces_last_sync_warning_context(self):
        today = fields.Date.context_today(self.instance)
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goals_unavailable,
        ):
            self.instance.action_sync_now()

        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": self.instance.id,
                "date_from": today - timedelta(days=1),
                "date_to": today,
            }
        )

        self.assertEqual(wizard.last_sync_state, "partial")
        self.assertEqual(wizard.last_sync_warning_count, 4)
        self.assertIn("Goal summary unavailable", wizard.last_sync_warning_summary)
        self.assertEqual(wizard.latest_sync_log_id, self.instance.latest_sync_log_id)

        action = wizard.action_open_latest_sync_log()
        self.assertEqual(action["res_id"], self.instance.latest_sync_log_id.id)

    def test_dashboard_applies_date_presets_on_create(self):
        today = fields.Date.context_today(self.instance)
        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": self.instance.id,
                "date_range_preset": "7d",
            }
        )

        self.assertEqual(wizard.date_to, today)
        self.assertEqual(wizard.date_from, today - timedelta(days=6))
        self.assertIn("Last 7 days", wizard.selected_range_label)

    def test_dashboard_builds_readable_scope_and_sync_guidance(self):
        today = fields.Date.context_today(self.instance)
        with patch(
            (
                "odoo.addons.matomo_analytics.models.matomo_instance."
                "MatomoInstance._do_post"
            ),
            autospec=True,
            side_effect=self._fake_do_post_goals_unavailable,
        ):
            self.instance.action_sync_now()

        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": self.instance.id,
                "date_from": today - timedelta(days=1),
                "date_to": today,
                "comparison_enabled": True,
            }
        )

        self.assertIn("Main Site", wizard.report_scope_summary)
        self.assertIn(str(today), wizard.report_scope_summary)
        self.assertIn("Comparison period", wizard.comparison_scope_summary)
        self.assertIn("partial data", wizard.sync_status_summary)
        self.assertIn("Warnings: 4.", wizard.sync_status_summary)
        self.assertIn("current period", wizard.data_quality_summary)
        self.assertIn("comparison period", wizard.data_quality_summary)

    def test_dashboard_report_actions_apply_current_scope(self):
        today = fields.Date.context_today(self.instance)
        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": self.instance.id,
                "date_from": today - timedelta(days=6),
                "date_to": today - timedelta(days=1),
            }
        )

        traffic_action = wizard.action_open_traffic_report()
        self.assertIn(wizard.selected_range_label, traffic_action["name"])
        self.assertEqual(
            traffic_action["domain"],
            [
                ("instance_id", "=", self.instance.id),
                ("date", ">=", today - timedelta(days=6)),
                ("date", "<=", today - timedelta(days=1)),
            ],
        )
        self.assertEqual(
            traffic_action["context"]["search_default_group_by_channel"], 1
        )

        content_action = wizard.action_open_content_report()
        self.assertEqual(
            content_action["context"]["search_default_group_by_metric_type"], 1
        )
        self.assertIn(
            ("metric_type", "in", ["page", "landing", "exit"]),
            content_action["domain"],
        )

        daily_trend_action = wizard.action_open_daily_trend()
        self.assertEqual(
            daily_trend_action["context"]["search_default_group_by_date"], 1
        )

        conversion_action = wizard.action_open_conversion_report()
        self.assertEqual(
            conversion_action["context"]["search_default_group_by_goal"], 1
        )

        country_action = wizard.action_open_country_report()
        self.assertEqual(
            country_action["context"]["search_default_group_by_country"], 1
        )

        referrer_action = wizard.action_open_referrer_report()
        self.assertEqual(
            referrer_action["context"]["search_default_group_by_referrer"], 1
        )

        top_pages_action = wizard.action_open_top_pages_report()
        self.assertEqual(top_pages_action["context"]["search_default_filter_page"], 1)
        self.assertIn(("metric_type", "=", "page"), top_pages_action["domain"])

    def test_dashboard_refresh_reloads_current_view(self):
        today = fields.Date.context_today(self.instance)
        wizard = self.env["matomo.analytics.dashboard"].create(
            {
                "instance_id": self.instance.id,
                "date_from": today - timedelta(days=6),
                "date_to": today - timedelta(days=1),
            }
        )

        action = wizard.action_refresh()

        self.assertEqual(
            action,
            {
                "type": "ir.actions.client",
                "tag": "reload",
            },
        )
