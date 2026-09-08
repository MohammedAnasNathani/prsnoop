"""Model, stats, and fetcher behavior tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prsnoop.fetch import _repo_of, fetch_user_activity
from prsnoop.models import PRRecord
from prsnoop.stats import build_activity, build_stats

# ------------------------------------------------------------------- models

class TestPRRecord:
    def test_days_to_merge(self, sample_prs):
        merged_fast, merged_slow, open_pr = sample_prs
        assert merged_fast.days_to_merge == pytest.approx(2.0)
        assert merged_slow.days_to_merge == pytest.approx(20.0)
        assert open_pr.days_to_merge is None

    def test_from_api_merged_state(self, now):
        record = PRRecord.from_api(
            {
                "number": 1, "title": "t", "html_url": "u", "state": "closed",
                "created_at": "2026-07-10T00:00:00Z", "merged_at": "2026-07-12T00:00:00Z",
                "additions": 1, "deletions": 1, "changed_files": 1,
            },
            repo="o/r",
        )
        assert record.state == "merged"
        assert record.merged_at == datetime(2026, 7, 12, tzinfo=timezone.utc)

    def test_from_api_open_state(self):
        record = PRRecord.from_api(
            {
                "number": 1, "title": "t", "html_url": "u", "state": "open",
                "created_at": "2026-07-10T00:00:00Z", "merged_at": None,
            },
            repo="o/r",
        )
        assert record.state == "open"
        assert record.merged_at is None

    def test_to_dict_roundtrip_dates(self, sample_prs):
        d = sample_prs[0].to_dict()
        assert d["created_at"] == "2026-07-10T12:00:00Z"
        assert d["merged_at"] == "2026-07-12T12:00:00Z"


# -------------------------------------------------------------------- stats

class TestBuildStats:
    def test_counts(self, activity):
        s = activity.stats
        assert s.prs_authored == 3
        assert s.prs_merged == 2
        assert s.prs_open == 1
        assert s.prs_closed_unmerged == 0
        assert s.reviews_given == 1
        assert s.issues_opened == 1

    def test_lines(self, activity):
        s = activity.stats
        assert s.lines_added == 42 + 310 + 15
        assert s.lines_deleted == 7 + 88 + 3

    def test_merge_rate(self, activity):
        assert activity.stats.merge_rate == pytest.approx(2 / 3, abs=1e-4)

    def test_median_days_to_merge(self, activity):
        # merge times are 2.0 and 20.0 days
        assert activity.stats.median_days_to_merge == pytest.approx(11.0)

    def test_top_repos_and_distinct(self, activity):
        s = activity.stats
        assert s.distinct_repos == 3
        # Three repos, one PR each: every repo appears exactly once.
        assert dict(s.top_repos) == {
            "aio-libs/yarl": 1,
            "agronholm/anyio": 1,
            "jd/tenacity": 1,
        }

    def test_top_labels_counts_and_ignores_empty(self, activity):
        activity.prs[0].labels = ["bug", "python", ""]
        activity.prs[1].labels = ["bug"]
        activity.stats = build_stats(activity)
        assert activity.stats.top_labels == [("bug", 2), ("python", 1)]

    def test_top_labels_maximum(self, now):
        prs = [
            PRRecord(
                repo=f"org/repo-{index}", number=index, title="t", url="u", state="open",
                created_at=now, merged_at=None, additions=0, deletions=0, changed_files=0,
                labels=[f"label-{index}"],
            )
            for index in range(11)
        ]
        assert len(build_activity("octocat", prs, [], [], now=now).stats.top_labels) == 10

    def test_empty_activity(self, now):
        empty = build_activity("nobody", [], [], [], now=now)
        s = empty.stats
        assert s.prs_authored == 0
        assert s.merge_rate == 0.0
        assert s.median_days_to_merge is None
        assert s.top_repos == []
        assert s.top_labels == []


# -------------------------------------------------------------------- fetch

class TestFetchUserActivity:
    def test_fetch_assembles_everything(self, fake_client, now):
        prs, reviews, issues, enriched = fetch_user_activity(
            fake_client, "octocat", days=30
        )
        assert enriched is True
        assert len(prs) == 2
        assert {p.repo for p in prs} == {"aio-libs/yarl", "jd/tenacity"}
        # yarl PR enriched with detail stats
        yarl = next(p for p in prs if p.repo == "aio-libs/yarl")
        assert (yarl.additions, yarl.deletions, yarl.changed_files) == (42, 7, 3)
        assert yarl.state == "merged"
        # tenacity PR is open
        tenacity = next(p for p in prs if p.repo == "jd/tenacity")
        assert tenacity.state == "open"
        assert len(reviews) == 1
        assert reviews[0].state == "APPROVED"
        assert reviews[0].repo == "voltagebots/agent-guard"
        assert len(issues) == 1
        assert issues[0].comments == 2

    def test_fetch_no_reviews_flag(self, fake_client):
        prs, reviews, issues, _ = fetch_user_activity(
            fake_client, "octocat", days=30, include_reviews=False
        )
        assert reviews == []
        assert len(prs) == 2
        # The reviewer-search route must not have been touched.
        assert not any(
            c[1] and "commenter:" in str(c[1].get("q", "")) for c in fake_client.calls
        )


class TestRepoOf:
    def test_extracts_owner_slash_name(self):
        assert (
            _repo_of({"repository_url": "https://api.github.com/repos/aio-libs/yarl"})
            == "aio-libs/yarl"
        )
