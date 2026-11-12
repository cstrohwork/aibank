(async () => {
  try {
    const response = await fetch("./config.json", {cache: "no-store"});
    if (!response.ok) return;
    const config = await response.json();
    const url = new URL(config.signupUrl);
    // Only a provider-hosted signup form; no subscriber data passes through GitHub.
    if (url.protocol !== "https:" || !url.hostname.endsWith(".sibforms.com") || url.username || url.password) return;
    const link = document.getElementById("signup");
    link.href = url.href;
    link.hidden = false;
    document.getElementById("status").textContent = "Select your preferences on our secure signup form.";
    document.getElementById("consent").hidden = false;
  } catch (_) { /* Keep the truthful unavailable state until configured. */ }
})();
