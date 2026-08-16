const form = document.querySelector("[data-contribution-form]");
const result = document.querySelector("[data-contribution-result]");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(form).entries());
  ["landmark_kind", "province_name", "city_name", "source_publisher", "source_title"].forEach((key) => {
    if (!payload[key]?.trim()) delete payload[key];
  });
  const submitButton = form.querySelector("button[type='submit']");
  submitButton.disabled = true;
  result.textContent = "正在提交…";
  try {
    const response = await fetch("/api/v1/contributions/landmarks", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify(payload) });
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "提交失败，请检查填写内容。");
    result.textContent = `提交已记录：${body.contributor_name}，条目编号 #${body.landmark_id}，等待审核。`;
    form.reset();
  } catch (error) { result.textContent = error.message; } finally { submitButton.disabled = false; }
});
