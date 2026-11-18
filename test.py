import asyncio
import json
from types import SimpleNamespace

import httpx

import app.main as app_main
from app.main import (
    AIPlanHistory,
    APPlan,
    BackgroundProject,
    GPA,
    Profile,
    SatAct,
    SessionLocal,
    StandardTest,
    User,
    app,
)


SMOKE_USERNAME = "smokeuser123"
SMOKE_PASSWORD = "12345678"


def cleanup_smoke_user():
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == SMOKE_USERNAME).first()
        if not user:
            return

        for model in [
            GPA,
            APPlan,
            StandardTest,
            SatAct,
            BackgroundProject,
            Profile,
            AIPlanHistory,
        ]:
            db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)

        db.delete(user)
        db.commit()


async def main():
    app_main.DEEPSEEK_API_KEY = None
    cleanup_smoke_user()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.headers["x-content-type-options"] == "nosniff"
        assert health.headers["x-frame-options"] == "DENY"
        assert "default-src 'self'" in health.headers["content-security-policy"]

        pages = [
            "/login.html",
            "/register.html",
            "/dashboard.html",
            "/profile.html",
            "/courses.html",
            "/match.html",
            "/timeline.html",
            "/portfolio.html",
            "/guide.html",
            "/ai-plan.html",
            "/my-plans.html",
            "/settings.html",
            "/docs",
        ]
        for page in pages:
            assert (await client.get(page)).status_code == 200

        unauthorized = await client.get("/api/user/info")
        assert unauthorized.json()["code"] == 401

        catalog = await client.get("/api/courses")
        assert catalog.status_code == 200
        catalog_data = catalog.json()["data"]
        assert catalog_data["examYear"] == 2027
        assert catalog_data["courseCount"] == 43
        assert catalog_data["pilotCount"] == 3
        assert catalog_data["optimizationCoverageCount"] == 43
        catalog_by_name = {item["name"]: item for item in catalog_data["courses"]}
        assert all(
            item["primary"] and item["groups"] and isinstance(item["rigor"], int)
            for item in catalog_data["courses"]
        )
        assert "高中生物" in catalog_by_name["AP Biology"]["prerequisites"]
        assert "高中化学" in catalog_by_name["AP Biology"]["prerequisites"]
        assert "2027–28" in catalog_by_name["AP Networking"]["availability"]

        us_catalog = await client.get("/api/universities/us")
        assert us_catalog.status_code == 200
        us_catalog_data = us_catalog.json()["data"]
        assert us_catalog_data["schoolCount"] >= 40
        assert all(
            item["officialSources"]["application"].startswith("https://")
            and item["officialSources"]["international"].startswith("https://")
            for item in us_catalog_data["schools"]
        )
        missing_test_profile = app_main.build_us_school_matches({
            "targetCountry": "美国", "major": "工程", "unweightedGpa": 3.9
        })
        mit_match = next(item for item in missing_test_profile["matches"] if item["school"] == "Massachusetts Institute of Technology")
        assert mit_match["requirementsToCheck"]
        mock_test_profile = app_main.build_us_school_matches({
            "targetCountry": "美国", "major": "工程", "unweightedGpa": 3.9,
            "satAct": {"type": "SAT", "score": "1520", "scoreSource": "mock"},
        })
        mock_mit_match = next(item for item in mock_test_profile["matches"] if item["school"] == "Massachusetts Institute of Technology")
        assert any("模考" in item for item in mock_mit_match["requirementsToCheck"])
        caltech_language_profile = app_main.build_us_school_matches({
            "targetCountry": "美国", "major": "工程", "unweightedGpa": 3.9,
            "applicationContext": {"primaryEnglishInstruction": False},
            "languageTest": {"type": "雅思", "score": "7", "scoreSource": "official", "reading": "7", "listening": "7", "speaking": "6.5", "writing": "7"},
        })
        caltech_match = next(item for item in caltech_language_profile["matches"] if item["school"] == "California Institute of Technology")
        assert any(check["severity"] == "blocker" and "小分" in check["title"] for check in caltech_match["requirementChecks"])
        uc_variant_profile = app_main.build_us_school_matches({
            "targetCountry": "美国", "major": "工程", "unweightedGpa": 3.9,
            "languageTest": {"type": "雅思", "score": "7", "scoreSource": "official", "variant": "one_skill_retake"},
        })
        ucb_match = next(item for item in uc_variant_profile["matches"] if item["school"] == "University of California, Berkeley")
        assert any(check["severity"] == "blocker" and "版本" in check["title"] for check in ucb_match["requirementChecks"])

        # 进阶课程在基础课程适配度差时应承受更强降权。
        calc_weights = app_main.build_course_personalization({
            "coursePreferences": {
                "AP Precalculus": {
                    "perceivedDifficulty": 5,
                    "interest": 1,
                    "confidence": 1,
                }
            }
        })["courseWeights"]
        assert calc_weights["AP Calculus AB"]["adjustment"] < calc_weights["AP Precalculus"]["adjustment"]
        assert calc_weights["AP Calculus BC"]["adjustment"] < calc_weights["AP Calculus AB"]["adjustment"]

        register = await client.post(
            "/api/register",
            json={
                "username": SMOKE_USERNAME,
                "password": SMOKE_PASSWORD,
                "email": "smoke@example.com",
                "name": "冒烟学生",
                "current_grade_term": "10年级上",
                "ap_plans": [{"course": "AP Computer Science A", "score": 5}],
            },
        )
        assert register.status_code == 200
        assert register.json()["code"] == 200

        duplicate = await client.post(
            "/api/register",
            json={
                "username": SMOKE_USERNAME,
                "password": SMOKE_PASSWORD,
                "email": "smoke@example.com",
                "name": "重复用户",
                "current_grade_term": "10年级上",
            },
        )
        assert duplicate.status_code == 400

        login = await client.post(
            "/api/login",
            json={"username": SMOKE_USERNAME, "password": SMOKE_PASSWORD},
        )
        assert login.status_code == 200
        login_data = login.json()
        assert login_data["code"] == 200
        assert login_data["token"]
        assert "httponly" in login.headers["set-cookie"].lower()

        blocked_origin = await client.post(
            "/api/user/settings",
            headers={"Origin": "https://attacker.example"},
            json={
                "email": "blocked@example.com",
                "name": "不应写入",
                "current_grade_term": "10年级上",
            },
        )
        assert blocked_origin.status_code == 403

        headers = {"Authorization": f"Bearer {login_data['token']}"}
        # HttpOnly Cookie 可独立完成鉴权；Bearer Token 继续兼容 API 客户端。
        user_info = await client.get("/api/user/info")
        assert user_info.status_code == 200
        assert user_info.json()["code"] == 200

        ap_plans = await client.get("/api/ap/plans")
        assert ap_plans.status_code == 200
        assert ap_plans.json()["code"] == 200
        assert ap_plans.json()["data"] == [
            {"course": "AP Computer Science A", "score": 5}
        ]
        with SessionLocal() as db:
            user = db.query(User).filter(User.username == SMOKE_USERNAME).one()
            assert db.query(Profile).filter(Profile.user_id == user.id).count() == 1
            assert db.query(APPlan).filter(APPlan.user_id == user.id).count() == 0

        onboarding = await client.get("/api/onboarding/status", headers=headers)
        assert onboarding.status_code == 200
        assert onboarding.json()["data"]["requires_onboarding"] is True

        profile_payload = {
            "grade": "10年级上",
            "targetCountry": "美国",
            "major": "计算机",
            "weightedGpa": "4.0",
            "unweightedGpa": "3.7",
            "apCourses": [
                {"course": "AP Computer Science A", "score": "5", "status": "completed", "scoreSource": "official", "examYear": "2026"},
                {"course": "AP Calculus BC", "score": "5", "status": "ongoing", "scoreSource": "estimated", "examYear": "2027"},
                {"course": "AP Physics 1: Algebra-Based", "status": "planned", "scoreSource": "", "examYear": "2027"},
            ],
            "satAct": {"type": "SAT", "score": "1450", "scoreSource": "mock", "verbal": "710", "math": "740"},
            "languageTest": {"type": "托福", "score": "100", "scoreSource": "mock", "reading": "27", "listening": "25", "speaking": "23", "writing": "25"},
            "activity": {"type": "竞赛", "description": "参加校内编程竞赛"},
            "academicContext": {"graduationYear": "2028", "gpaScale": "4.0", "curriculum": "AP"},
            "applicationContext": {"applicationRound": "ED/EA", "englishMediumYears": "2", "financialAidNeeded": "yes"},
        }
        save_profile = await client.post(
            "/api/profile/save",
            headers=headers,
            json=profile_payload,
        )
        assert save_profile.status_code == 200
        save_profile_data = save_profile.json()
        assert save_profile_data["code"] == 200
        assert save_profile_data["data"]["analysis"]["profile"]["majorTrack"] == "计算机"
        assert save_profile_data["data"]["analysis"]["profile"]["apCount"] == 3
        assert save_profile_data["data"]["analysis"]["profile"]["apCompletedCount"] == 1

        onboarding = await client.get("/api/onboarding/status", headers=headers)
        assert onboarding.json()["data"]["completed"] is True

        analysis = await client.get("/api/planning/analysis", headers=headers)
        assert analysis.status_code == 200
        analysis_data = analysis.json()["data"]
        assert analysis_data["profile"]["majorTrack"] == "计算机"
        assert "AP Calculus BC" in analysis_data["coursePlan"]["includedCore"]
        assert analysis_data["coursePlan"]["balance"]

        timeline = await client.get("/api/timeline", headers=headers)
        assert timeline.status_code == 200
        timeline_data = timeline.json()["data"]
        assert len(timeline_data["tracks"]) == 6
        assert timeline_data["summary"]["topFocus"]["id"]
        timeline_task_id = timeline_data["summary"]["topFocus"]["id"]
        timeline_progress = await client.post(
            "/api/timeline/progress",
            headers=headers,
            json={
                "taskId": timeline_task_id,
                "status": "in_progress",
                "completedSteps": [f"{timeline_task_id}-0"],
                "note": "已开始处理第一项",
            },
        )
        assert timeline_progress.status_code == 200
        updated_timeline = timeline_progress.json()["data"]
        updated_task = next(
            task for track in updated_timeline["tracks"] for task in track["tasks"]
            if task["id"] == timeline_task_id
        )
        assert updated_task["status"] == "in_progress"
        assert updated_task["progress"] > 0
        assert updated_task["note"] == "已开始处理第一项"

        ai_chat = await client.post(
            "/api/ai-chat",
            headers=headers,
            json={"message": "我新增了 AP Calculus BC 5分，请更新我的规划。"},
        )
        assert ai_chat.status_code == 200
        ai_chat_data = ai_chat.json()
        assert ai_chat_data["code"] == 200
        assert ai_chat_data["data"]["detected_updates"]

        profile = await client.get("/api/profile/me", headers=headers)
        ap_courses = profile.json()["data"]["apCourses"]
        assert any(item["course"] == "AP Calculus BC" for item in ap_courses)
        profile_data = profile.json()["data"]
        assert profile_data["languageTest"]["speaking"] == "23"
        assert profile_data["languageTest"]["scoreSource"] == "mock"
        assert profile_data["applicationContext"]["englishMediumYears"] == "2"

        psychology_interest = await client.post(
            "/api/ai-chat",
            headers=headers,
            json={"message": "我除了CS，还喜欢心理学，AP心理适合选吗？"},
        )
        assert psychology_interest.status_code == 200
        interest_data = psychology_interest.json()
        assert "课程兴趣：AP Psychology" in "; ".join(interest_data["data"]["detected_updates"])

        profile = await client.get("/api/profile/me", headers=headers)
        updated_profile_data = profile.json()["data"]
        assert "AP Psychology" in updated_profile_data["courseInterests"]
        assert not any(item["course"] == "AP Psychology" for item in updated_profile_data["apCourses"])

        analysis = await client.get("/api/planning/analysis", headers=headers)
        balance_courses = analysis.json()["data"]["coursePlan"]["balance"]
        assert balance_courses and balance_courses[0] == "AP Psychology"

        # 个人评价会传播到同学科，并为仍需满足的自然科学组提供替代课。
        engineering_payload = dict(profile_payload)
        engineering_payload["major"] = "工程"
        engineering_profile = await client.post(
            "/api/profile/save", headers=headers, json=engineering_payload
        )
        assert engineering_profile.status_code == 200

        school_matches = await client.get("/api/school-matches", headers=headers)
        assert school_matches.status_code == 200
        school_match_data = school_matches.json()["data"]
        assert school_match_data["countryMatch"] is True
        assert school_match_data["profileSignals"]["majorTrack"] == "工程"
        assert len(school_match_data["matches"]) >= 40
        assert all(
            item["officialSources"]["application"].startswith("https://")
            for item in school_match_data["matches"]
        )
        match_sort_keys = [
            (sum(check["severity"] == "blocker" for check in item["requirementChecks"]), len(item["requirementsToCheck"]), -item["fitScore"], -item["majorStrength"], item["school"])
            for item in school_match_data["matches"]
        ]
        assert match_sort_keys == sorted(match_sort_keys)

        physics_preference = await client.post(
            "/api/course-preferences",
            headers=headers,
            json={
                "course": "AP Physics 1: Algebra-Based",
                "perceivedDifficulty": 5,
                "interest": 1,
                "confidence": 1,
                "note": "多步骤受力分析很吃力",
            },
        )
        assert physics_preference.status_code == 200
        preference_data = physics_preference.json()["data"]
        weights = preference_data["personalization"]["courseWeights"]
        assert len(weights) == 43
        assert weights["AP Physics 1: Algebra-Based"]["adjustment"] < 0
        assert weights["AP Physics 2: Algebra-Based"]["adjustment"] < weights["AP Physics 1: Algebra-Based"]["adjustment"]
        assert weights["AP Physics C: Mechanics"]["adjustment"] < weights["AP Physics 2: Algebra-Based"]["adjustment"]
        assert weights["AP Physics C: Electricity and Magnetism"]["adjustment"] < weights["AP Physics C: Mechanics"]["adjustment"]
        assert weights["AP Biology"]["adjustment"] > 0
        assert weights["AP Chemistry"]["adjustment"] > 0
        assert weights["AP Environmental Science"]["adjustment"] > 0
        assert "AP Biology" in preference_data["coursePlan"]["alternatives"]
        assert "AP Environmental Science" in preference_data["coursePlan"]["alternatives"]
        assert "AP Physics C: Mechanics" not in preference_data["coursePlan"]["core"]
        assert "AP Physics C: Mechanics" in preference_data["coursePlan"]["deprioritized"]

        saved_preferences = await client.get("/api/course-preferences", headers=headers)
        saved_preference_data = saved_preferences.json()["data"]
        assert saved_preference_data["preferences"]["AP Physics 1: Algebra-Based"]["note"] == "多步骤受力分析很吃力"
        assert saved_preference_data["personalization"]["evaluatedCount"] == 1

        personalized_analysis = await client.get("/api/planning/analysis", headers=headers)
        personalized_data = personalized_analysis.json()["data"]
        assert personalized_data["personalization"]["familySignals"]["physics"] < 0
        assert personalized_data["coursePlan"]["alternatives"]

        personalized_chat = await client.post(
            "/api/ai-chat",
            headers=headers,
            json={"message": "结合我的个人课程评价，重新解释工程方向的AP选择。"},
        )
        assert personalized_chat.status_code == 200
        personalized_chat_data = personalized_chat.json()["data"]
        assert personalized_chat_data["analysis"]["personalization"]["evaluatedCount"] == 1
        assert personalized_chat_data["analysis"]["coursePlan"]["alternatives"]

        class FakeUsage:
            def model_dump(self):
                return {"server_tool_use": {"tool_search": 1, "tool_fetch": 0}}

        class FakeResponses:
            def create(self, **kwargs):
                assert kwargs["model"] == "deepseek-v4-pro"
                assert kwargs["reasoning"] == {"effort": "low"}
                assert kwargs["tools"] == [{"type": "web_search"}]
                assert kwargs["stream"] is True
                yield SimpleNamespace(type="response.reasoning_text.delta")
                yield SimpleNamespace(type="response.web_search_call.searching")
                yield SimpleNamespace(type="response.output_text.delta", delta="找到官网资料。")
                yield SimpleNamespace(
                    type="response.completed",
                    response=SimpleNamespace(usage=FakeUsage()),
                )

        class FakeDeepSeekClient:
            def __init__(self, **kwargs):
                assert kwargs["api_key"] == "test-key"
                self.responses = FakeResponses()

        original_openai = app_main.OpenAI
        app_main.OpenAI = FakeDeepSeekClient
        app_main.DEEPSEEK_API_KEY = "test-key"
        try:
            streamed = await client.post(
                "/api/ai-chat",
                headers=headers,
                json={"message": "请联网查看最新的AP课程安排。我新增 SAT 1490。", "web_search": True},
            )
        finally:
            app_main.OpenAI = original_openai
            app_main.DEEPSEEK_API_KEY = None
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("text/event-stream")
        assert "正在搜索网页" in streamed.text
        assert "找到官网资料。" in streamed.text
        done_frame = next(frame for frame in streamed.text.split("\n\n") if frame.startswith("event: done"))
        done_data = json.loads(next(line[6:] for line in done_frame.splitlines() if line.startswith("data: ")))
        assert done_data["source"] == "deepseek_search"
        assert done_data["searched"] is True
        assert done_data["saved"] is True
        assert done_data["detected_updates"]
        with SessionLocal() as history_db:
            saved_history = history_db.query(AIPlanHistory).filter(AIPlanHistory.id == done_data["id"]).one()
            assert saved_history.answer.endswith("找到官网资料。")
        updated_profile = await client.get("/api/profile/me", headers=headers)
        assert updated_profile.json()["data"]["satAct"]["score"] == "1490"
        assert (await client.delete(f"/api/ai-plans/{done_data['id']}", headers=headers)).json()["code"] == 200

        failed_stream = await client.post(
            "/api/ai-chat",
            headers=headers,
            json={"message": "请联网查看最新的AP课程安排。", "web_search": True},
        )
        fallback_frame = next(frame for frame in failed_stream.text.split("\n\n") if frame.startswith("event: done"))
        fallback_data = json.loads(next(line[6:] for line in fallback_frame.splitlines() if line.startswith("data: ")))
        assert fallback_data["source"] == "local_fallback"
        assert fallback_data["saved"] is True
        assert "event: reset" in failed_stream.text
        assert (await client.delete(f"/api/ai-plans/{fallback_data['id']}", headers=headers)).json()["code"] == 200

        invalid_preference = await client.post(
            "/api/course-preferences",
            headers=headers,
            json={
                "course": "AP Imaginary Subject",
                "perceivedDifficulty": 3,
                "interest": 3,
                "confidence": 3,
                "note": "",
            },
        )
        assert invalid_preference.status_code == 422

        irrelevant = await client.post(
            "/api/ai-chat",
            headers=headers,
            json={"message": "帮我写一首关于晚餐的诗"},
        )
        assert irrelevant.status_code == 200
        assert irrelevant.json()["data"]["source"] == "local_reject"

        settings = await client.post(
            "/api/user/settings",
            headers=headers,
            json={
                "email": "updated-smoke@example.com",
                "name": "冒烟学生",
                "current_grade_term": "10年级下",
            },
        )
        assert settings.json()["code"] == 200
        profile = await client.get("/api/profile/me", headers=headers)
        assert profile.json()["data"]["grade"] == "10年级下"

        histories = await client.get("/api/ai-plans", headers=headers)
        assert histories.json()["code"] == 200
        assert len(histories.json()["data"]) == 3
        plan_id = histories.json()["data"][0]["id"]
        deleted = await client.delete(f"/api/ai-plans/{plan_id}", headers=headers)
        assert deleted.json()["code"] == 200

        logout = await client.post("/api/logout")
        assert logout.json()["code"] == 200
        assert (await client.get("/api/user/info")).json()["code"] == 401

        app_main.rate_limit_buckets.clear()
        for _ in range(10):
            attempt = await client.post(
                "/api/login",
                json={"username": "missing-user", "password": "not-a-password"},
            )
            assert attempt.status_code == 200
        limited = await client.post(
            "/api/login",
            json={"username": "missing-user", "password": "not-a-password"},
        )
        assert limited.status_code == 429

    cleanup_smoke_user()
    print("后端冒烟测试通过")


if __name__ == "__main__":
    asyncio.run(main())
