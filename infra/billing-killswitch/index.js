const { GoogleAuth } = require("google-auth-library");

const BILLING_SCOPE = "https://www.googleapis.com/auth/cloud-billing";
const METADATA_PROJECT_ID = "GOOGLE_CLOUD_PROJECT";

function readProjectId() {
  return (
    process.env.PROJECT_ID ||
    process.env.GCP_PROJECT ||
    process.env[METADATA_PROJECT_ID] ||
    ""
  );
}

function parseThreshold() {
  const raw = process.env.BUDGET_THRESHOLD || "1";
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function decodeBudgetPayload(cloudEvent) {
  const message = cloudEvent?.data?.message;
  const encoded = message?.data;
  if (!encoded) return null;
  try {
    const decoded = Buffer.from(encoded, "base64").toString("utf-8");
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

async function disableBilling(projectId) {
  const auth = new GoogleAuth({ scopes: BILLING_SCOPE });
  const client = await auth.getClient();
  const url = `https://cloudbilling.googleapis.com/v1/projects/${projectId}/billingInfo`;
  const response = await client.request({
    url,
    method: "PUT",
    data: { billingAccountName: "" },
  });
  return response.data;
}

exports.disableBillingOnBudget = async (cloudEvent) => {
  const projectId = readProjectId();
  if (!projectId) {
    console.error("Missing project id.");
    return;
  }

  const payload = decodeBudgetPayload(cloudEvent);
  if (!payload) {
    console.error("Missing budget payload.");
    return;
  }

  const threshold = parseThreshold();
  const alertExceeded = Number(payload.alertThresholdExceeded ?? 0);
  const forecastExceeded = Number(payload.forecastThresholdExceeded ?? 0);

  if (alertExceeded < threshold && forecastExceeded < threshold) {
    console.log("Budget below threshold.", { alertExceeded, forecastExceeded, threshold });
    return;
  }

  console.log("Disabling billing for project.", {
    projectId,
    alertExceeded,
    forecastExceeded,
    threshold,
    budget: payload.budgetDisplayName ?? payload.budgetName ?? "unknown",
  });

  const result = await disableBilling(projectId);
  console.log("Billing disabled.", result);
};
