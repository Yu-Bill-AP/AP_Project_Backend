"""Regression checks for policy errors that can change an applicant's match list."""
import copy
import os
import unittest
from unittest.mock import patch

import httpx

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_CREATE_SCHEMA"] = "false"
os.environ["CREATE_DEMO_USER"] = "false"
os.environ["APP_ENV"] = "development"

from app.main import build_school_requirement_checks, build_us_school_matches, resolve_school_test_policy
from app.university_catalog import DEFAULT_ENTRY_YEAR, UNIVERSITY_BY_NAME, US_UNIVERSITY_CATALOG
import app.main as app_main


class UniversityRequirementsTests(unittest.TestCase):
    def profile(self, **extra):
        return {"targetCountry": "美国", "major": "工程", "unweightedGpa": 3.9, **extra}

    def checks(self, name, language=None, context=None, **extra):
        profile = self.profile(languageTest=language or {}, applicationContext=context or {}, **extra)
        return build_school_requirement_checks(UNIVERSITY_BY_NAME[name], profile, "工程")[0]

    def match(self, name, profile, year=DEFAULT_ENTRY_YEAR):
        return next(s for s in build_us_school_matches(profile, year)["matches"] if s["school"] == name)

    def official(self, test, score, **extra):
        return {"type": test, "score": score, "scoreSource": "official", **extra}

    def test_every_school_has_a_dated_review_and_specialized_sources(self):
        self.assertEqual(len(US_UNIVERSITY_CATALOG), 41)
        self.assertEqual(len(UNIVERSITY_BY_NAME), 41)
        for school in US_UNIVERSITY_CATALOG:
            review = school["officialReview"]
            self.assertEqual(review["checkedAt"], "2026-11-18")
            self.assertEqual(review["entryYear"], 2027)
            self.assertTrue(all(url.startswith("https://") for url in school["officialSources"].values()))
            for key in ("application", "international", "testing", "english"):
                self.assertIn(key, school["officialSources"])
            self.assertEqual(review["status"] == "partial", bool(review["pendingFields"]))

    def test_yale_accepts_duolingo(self):
        checks = self.checks("Yale University", self.official("多邻国", 130))
        self.assertFalse(any(c["severity"] == "blocker" for c in checks))

    def test_princeton_policy_changes_with_entry_year(self):
        school = UNIVERSITY_BY_NAME["Princeton University"]
        self.assertEqual(resolve_school_test_policy(school, 2027, "工程", {})[0], "test_optional")
        self.assertEqual(resolve_school_test_policy(school, 2028, "工程", {})[0], "required_sat_act")

    def test_columbia_announced_change_applies_from_fall_2028(self):
        school = UNIVERSITY_BY_NAME["Columbia University"]
        self.assertEqual(resolve_school_test_policy(school, 2027, "工程", {})[0], "test_optional")
        self.assertEqual(resolve_school_test_policy(school, 2028, "工程", {})[0], "required_sat_act_with_access_exceptions")
        self.assertEqual(school["officialReview"]["verifiedFields"], ["testing"])
        self.assertIn("english", school["officialReview"]["pendingFields"])

    def test_unc_testing_requires_explicit_weighted_four_point_gpa(self):
        school = UNIVERSITY_BY_NAME["University of North Carolina at Chapel Hill"]
        for gpa, policy in [(2.79, "required_sat_act"), (2.8, "test_optional"), (3.9, "test_optional")]:
            profile = self.profile(weightedGpa=gpa, academicContext={"gpaScale": "4.0"})
            self.assertEqual(resolve_school_test_policy(school, 2027, "工程", profile)[0], policy)
        for extra in [{}, {"weightedGpa": 3.9}, {"weightedGpa": 3.9, "academicContext": {"gpaScale": "5.0"}},
                      {"weightedGpa": 4.2, "academicContext": {"gpaScale": "4.0"}}]:
            profile = self.profile(**extra)
            self.assertEqual(resolve_school_test_policy(school, 2027, "工程", profile)[0], "conditional_sat_act")
            self.assertTrue(self.match(school["name"], profile)["requirementsToCheck"])

    def test_unc_testing_minimum_is_only_enforced_on_the_required_gpa_path(self):
        name = "University of North Carolina at Chapel Hill"
        for test, score, blocked in [("SAT", 929, True), ("SAT", 930, False), ("ACT", 16, True), ("ACT", 17, False)]:
            profile = self.profile(weightedGpa=2.7, academicContext={"gpaScale": "4.0"},
                                   languageTest=self.official("雅思", 8), satAct=self.official(test, score))
            matched = self.match(name, profile)
            self.assertEqual(any(c["severity"] == "blocker" for c in matched["requirementChecks"]), blocked)
        profile["weightedGpa"] = 3.0
        profile["satAct"] = self.official("SAT", 900)
        self.assertFalse(any(c["severity"] == "blocker" for c in self.match(name, profile)["requirementChecks"]))
        profile["weightedGpa"] = 2.7
        profile["satAct"] = {"type": "SAT", "score": 1500, "scoreSource": "mock"}
        self.assertTrue(self.match(name, profile)["requirementsToCheck"])

    def test_unc_english_reference_scores_are_not_hard_minimums(self):
        checks = self.checks("University of North Carolina at Chapel Hill", self.official("雅思", 7))
        self.assertTrue(any(c["severity"] == "warning" and "参考" in c["title"] for c in checks))
        self.assertFalse(any(c["severity"] == "blocker" for c in checks))

    def test_uf_does_not_invent_a_freshman_english_score_threshold(self):
        checks = self.checks("University of Florida", self.official("托福", 60, scoreScale="legacy120"))
        self.assertTrue(any(c["severity"] == "warning" and "总分门槛" in c["title"] for c in checks))
        self.assertFalse(any(c["severity"] == "pass" for c in checks))
        self.assertFalse(any(c["severity"] == "blocker" for c in checks))

    def test_non_exhaustive_uf_exam_list_does_not_reject_unlisted_exam(self):
        checks = self.checks("University of Florida", self.official("多邻国", 140))
        self.assertTrue(any(c["severity"] == "warning" and "类型" in c["title"] for c in checks))
        self.assertFalse(any(c["severity"] in {"pass", "blocker"} for c in checks))

    def test_source_conflicts_are_visible_even_when_core_policies_were_reviewed(self):
        result = build_us_school_matches(self.profile(languageTest=self.official("雅思", 8)))
        names = {"University of Florida", "University of North Carolina at Chapel Hill"}
        self.assertEqual(set(result["reviewCoverage"]["sourceConflictSchools"]), names)
        for matched in result["matches"]:
            if matched["school"] in names:
                self.assertEqual(matched["officialReview"]["status"], "reviewed")
                self.assertTrue(matched["officialSourceConflicts"])
                self.assertTrue(any(c["severity"] == "warning" and "差异" in c["title"] for c in matched["requirementChecks"]))

    def test_vanderbilt_announced_change_is_not_applied_early(self):
        school = UNIVERSITY_BY_NAME["Vanderbilt University"]
        self.assertEqual(resolve_school_test_policy(school, 2028, "工程", {})[0], "test_optional")
        self.assertEqual(resolve_school_test_policy(school, 2029, "工程", {})[0], "required_sat_act")

    def test_cmu_policies_follow_the_college(self):
        school = UNIVERSITY_BY_NAME["Carnegie Mellon University"]
        for major, policy in [("计算机", "required_sat_act"), ("工程", "test_flexible"), ("艺术", "test_optional")]:
            self.assertEqual(resolve_school_test_policy(school, 2027, major, {})[0], policy)

    def test_dartmouth_us_high_school_is_not_on_the_international_alternative_path(self):
        profile = self.profile(applicationContext={"secondarySchoolCountry": "美国"})
        policy = resolve_school_test_policy(UNIVERSITY_BY_NAME["Dartmouth College"], 2027, "工程", profile)
        self.assertEqual(policy[0], "required_sat_act")

    def test_uc_test_free_score_is_invariant_to_sat(self):
        base = self.profile(languageTest=self.official("雅思", 8))
        with_sat = {**base, "satAct": self.official("SAT", 1600)}
        before = {m["school"]: m for m in build_us_school_matches(base)["matches"]}
        after = {m["school"]: m for m in build_us_school_matches(with_sat)["matches"]}
        for name in before:
            if name.startswith("University of California,"):
                self.assertEqual(before[name]["fitScore"], after[name]["fitScore"], name)
                self.assertFalse(any("SAT" in gap for gap in before[name]["academicGaps"]), name)

    def test_optional_school_does_not_penalize_missing_sat(self):
        base = self.profile(languageTest=self.official("雅思", 8))
        self.assertEqual(self.match("Duke University", base)["fitScore"],
                         self.match("Duke University", {**base, "satAct": self.official("SAT", 1600)})["fitScore"])

    def test_berkeley_and_ucsd_do_not_use_generic_uc_english_minimums(self):
        for name, score in [("University of California, Berkeley", 85), ("University of California, San Diego", 82)]:
            checks = self.checks(name, self.official("托福", score, scoreScale="legacy120"))
            self.assertTrue(any(c["severity"] == "blocker" and "总分" in c["title"] for c in checks), name)

    def test_ucla_competitive_ielts_is_not_a_hard_cutoff(self):
        checks = self.checks("University of California, Los Angeles", self.official("雅思", 7))
        self.assertFalse(any(c["severity"] == "blocker" for c in checks))
        self.assertTrue(any(c["severity"] == "warning" and "参考" in c["title"] for c in checks))

    def test_caltech_subscore_minimum_is_enforced(self):
        checks = self.checks("California Institute of Technology",
                             self.official("雅思", 7, reading=7, listening=7, writing=7, speaking=6.5))
        self.assertTrue(any(c["severity"] == "blocker" and "小分" in c["title"] for c in checks))

    def test_rejected_variant_cannot_also_get_a_passing_score_check(self):
        checks = self.checks("University of California, Berkeley", self.official("雅思", 8, variant="one_skill_retake"))
        self.assertTrue(any(c["severity"] == "blocker" and "版本" in c["title"] for c in checks))
        self.assertFalse(any(c["severity"] == "pass" for c in checks))

    def test_unknown_variant_is_reviewed_instead_of_passing(self):
        checks = self.checks("Yale University", self.official("托福", 110, variant="other"))
        self.assertTrue(any(c["severity"] == "warning" and "版本" in c["title"] for c in checks))
        self.assertFalse(any(c["severity"] == "pass" for c in checks))

    def test_recommended_english_tests_do_not_create_hard_blockers(self):
        for name, test, score in [("Massachusetts Institute of Technology", "雅思", 6.5),
                                  ("Brown University", "雅思", 7), ("Duke University", "多邻国", 110)]:
            checks = self.checks(name, self.official(test, score))
            self.assertFalse(any(c["severity"] == "blocker" for c in checks), name)

    def test_english_medium_checkbox_does_not_replace_a_years_requirement(self):
        checks = self.checks("Princeton University", context={"primaryEnglishInstruction": True, "englishMediumYears": 1})
        self.assertFalse(any(c["severity"] == "pass" and "豁免" in c["title"] for c in checks))

    def test_cmu_does_not_gain_an_english_medium_waiver(self):
        checks = self.checks("Carnegie Mellon University", context={"primaryEnglishInstruction": True, "englishMediumYears": 8})
        self.assertFalse(any(c["severity"] == "pass" and "豁免" in c["title"] for c in checks))

    def test_caltech_explicit_primary_instruction_exemption_is_retained(self):
        checks = self.checks("California Institute of Technology", context={"primaryEnglishInstruction": True})
        self.assertTrue(any(c["severity"] == "pass" and "豁免" in c["title"] for c in checks))

    def test_planned_or_mock_ap_scores_cannot_prove_english(self):
        for status, source in [("planned", "official"), ("score_released", "mock")]:
            checks = self.checks("University of California, Berkeley", apCourses=[
                {"course": "AP English Language and Composition", "score": 5, "status": status, "scoreSource": source}
            ])
            self.assertFalse(any(c["severity"] == "pass" and "替代" in c["title"] for c in checks))
        checks = self.checks("University of California, Berkeley", apCourses=[
            {"course": "AP English Language and Composition", "score": 3, "status": "score_released", "scoreSource": "official"}
        ])
        self.assertTrue(any(c["severity"] == "pass" and "替代" in c["title"] for c in checks))

    def test_penn_score_date_is_checked(self):
        for date, expected in [("2025-03", True), ("2025-04", False), ("2026-09", False)]:
            checks = self.checks("University of Pennsylvania", self.official("雅思", 8, testDate=date))
            self.assertEqual(any(c["severity"] == "blocker" and "日期" in c["title"] for c in checks), expected)

    def test_bu_new_scale_is_not_invented_from_legacy_scores(self):
        checks = self.checks("Boston University", self.official("托福", 5, scoreScale="new6"))
        self.assertTrue(any("分制" in c["title"] and c["severity"] == "warning" for c in checks))
        self.assertFalse(any(c["severity"] == "pass" for c in checks))

    def test_cmu_toefl_essentials_is_not_compared_to_ibt(self):
        checks = self.checks("Carnegie Mellon University", self.official("托福", 11, variant="essentials"))
        self.assertFalse(any(c["severity"] == "blocker" for c in checks))

    def test_notre_dame_home_edition_restriction_is_independent_of_score(self):
        checks = self.checks("University of Notre Dame", self.official("托福", 115, variant="home_edition"))
        self.assertTrue(any(c["severity"] == "blocker" and "版本" in c["title"] for c in checks))

    def test_sat_section_can_prove_english_only_where_the_school_accepts_it(self):
        profile = self.profile(satAct=self.official("SAT", 1450, verbal=700))
        for name in ["Emory University", "University of California, Irvine"]:
            checks, _ = build_school_requirement_checks(UNIVERSITY_BY_NAME[name], profile, "工程")
            self.assertTrue(any(c["severity"] == "pass" and "替代" in c["title"] for c in checks), name)
        checks, _ = build_school_requirement_checks(UNIVERSITY_BY_NAME["University of California, Santa Barbara"], profile, "工程")
        self.assertFalse(any(c["severity"] == "pass" and "替代" in c["title"] for c in checks))

    def test_ambiguous_legacy_act_section_does_not_invent_an_english_waiver(self):
        profile = self.profile(satAct=self.official("ACT", 33, verbal=30))
        checks, _ = build_school_requirement_checks(UNIVERSITY_BY_NAME["Emory University"], profile, "工程")
        self.assertFalse(any(c["severity"] == "pass" and "替代" in c["title"] for c in checks))

    def test_verified_financial_aid_constraint_still_gets_a_followup(self):
        checks = self.checks("Boston College", self.official("雅思", 8), context={"financialAidNeeded": "yes"})
        self.assertTrue(any("资助" in c["title"] for c in checks))

    def test_unread_policies_and_future_english_do_not_get_a_false_pass(self):
        for name in ["Columbia University"]:
            checks = self.checks(name, self.official("雅思", 8))
            self.assertTrue(any(c["severity"] == "warning" and "核验" in c["title"] for c in checks), name)
            self.assertFalse(any(c["severity"] == "pass" for c in checks), name)
        checks, _ = build_school_requirement_checks(UNIVERSITY_BY_NAME["Yale University"],
            self.profile(languageTest=self.official("雅思", 5)), "工程", 2028)
        self.assertTrue(any(c["severity"] == "warning" for c in checks))
        self.assertFalse(any(c["severity"] == "blocker" for c in checks))

    def test_building_matches_does_not_mutate_review_data(self):
        before = copy.deepcopy(US_UNIVERSITY_CATALOG)
        build_us_school_matches(self.profile())
        build_us_school_matches(self.profile(major="计算机"), 2029)
        self.assertEqual(before, US_UNIVERSITY_CATALOG)


class UniversityRequirementsApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_metadata_and_entry_year_http_contract(self):
        app_main.app.dependency_overrides[app_main.get_db] = lambda: None
        try:
            with patch.object(app_main, "get_user_id_from_authorization", return_value=(1, None)), \
                    patch.object(app_main, "get_profile_data", return_value={"targetCountry": "美国", "major": "工程"}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url="http://testserver") as client:
                    catalog = (await client.get("/api/universities/us")).json()["data"]
                    self.assertEqual(catalog["schoolCount"], 41)
                    self.assertEqual(catalog["lastReviewed"], "2026-11-18")
                    result = (await client.get("/api/school-matches?entry_year=2028")).json()["data"]
                    self.assertEqual(result["entryYear"], 2028)
                    self.assertEqual(result["reviewCoverage"]["reviewedSchools"], 40)
                    self.assertEqual(result["reviewCoverage"]["pendingSchools"], ["Columbia University"])
                    self.assertEqual(len(result["reviewCoverage"]["sourceConflictSchools"]), 2)
                    princeton = next(s for s in result["matches"] if s["school"] == "Princeton University")
                    self.assertEqual(princeton["officialPolicies"]["testPolicyKey"], "required_sat_act")
                    for value in ["2026", "2036", "unknown"]:
                        response = await client.get("/api/school-matches", params={"entry_year": value})
                        self.assertEqual(response.status_code, 422)
        finally:
            app_main.app.dependency_overrides.pop(app_main.get_db, None)


if __name__ == "__main__":
    unittest.main()
