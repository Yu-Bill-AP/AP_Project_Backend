// 你的后端地址，和你本地服务保持一致
const BASE_URL = "http://127.0.0.1:8000";

// 1. 测试后端连接
async function checkHealth() {
    const res = await fetch(`${BASE_URL}/health`);
    const data = await res.json();
    document.getElementById("status").textContent = `后端状态：${data.status}`;
}

// 2. 获取AP规划数据并显示
async function getAPPlans() {
    const res = await fetch(`${BASE_URL}/api/ap/plans`);
    const data = await res.json();
    const list = document.getElementById("ap-list");
    
    data.data.forEach(plan => {
        const li = document.createElement("li");
        li.textContent = `${plan.course} - 分数：${plan.score}`;
        list.appendChild(li);
    });
}

// 页面加载完成后自动执行
window.onload = function() {
    checkHealth();
    getAPPlans();
};