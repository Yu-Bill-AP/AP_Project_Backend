import asyncio

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

        register = await client.post(
            "/api/register",
            json={
                "username": SMOKE_USERNAME,
                "password": SMOKE_PASSWORD,
                "email": "smoke@example.com",
                "name": "冒烟学生",
                "current_grade_term": "10年级上",
            },
        )
        assert register.status_code == 200
        assert register.json()["code"] == 200

        login = await client.post(
            "/api/login",
            json={"username": SMOKE_USERNAME, "password": SMOKE_PASSWORD},
        )
        assert login.status_code == 200
        login_data = login.json()
        assert login_data["code"] == 200
        assert login_data["token"]

        headers = {"Authorization": f"Bearer {login_data['token']}"}
        user_info = await client.get("/api/user/info", headers=headers)
        assert user_info.status_code == 200
        assert user_info.json()["code"] == 200

        ap_plans = await client.get("/api/ap/plans", headers=headers)
        assert ap_plans.status_code == 200
        assert ap_plans.json()["code"] == 200

        onboarding = await client.get("/api/onboarding/status", headers=headers)
        assert onboarding.status_code == 200
        assert onboarding.json()["data"]["requires_onboarding"] is True

        profile_payload = {
            "grade": "10年级上",
            "targetCountry": "美国",
            "major": "计算机",
            "weightedGpa": "4.0",
            "unweightedGpa": "3.7",
            "apCourses": [{"course": "AP Computer Science A", "score": "5"}],
            "satAct": {"type": "SAT", "score": "1450"},
            "languageTest": {"type": "托福", "score": "100"},
            "activity": {"type": "竞赛", "description": "参加校内编程竞赛"},
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

        onboarding = await client.get("/api/onboarding/status", headers=headers)
        assert onboarding.json()["data"]["completed"] is True

        analysis = await client.get("/api/planning/analysis", headers=headers)
        assert analysis.status_code == 200
        analysis_data = analysis.json()["data"]
        assert analysis_data["profile"]["majorTrack"] == "计算机"
        assert "AP Calculus BC" in analysis_data["coursePlan"]["core"]
        assert analysis_data["coursePlan"]["balance"]

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

    cleanup_smoke_user()
    print("后端冒烟测试通过")


if __name__ == "__main__":
    asyncio.run(main())
