/**
 * SporeDB Dashboard - Plotly chart initialization helpers.
 *
 * Fetches Plotly figure JSON from API endpoints and renders charts
 * client-side using Plotly.js.
 */

/**
 * Render a Plotly chart in the given container from an API endpoint.
 *
 * @param {string} divId - The DOM element ID for the chart container.
 * @param {string} endpointUrl - The API URL that returns Plotly figure JSON.
 */
async function renderChart(divId, endpointUrl) {
  const container = document.getElementById(divId);
  if (!container) {
    console.error("Chart container not found:", divId);
    return;
  }

  try {
    const resp = await fetch(endpointUrl, {
      credentials: "same-origin", // Send cookies for auth
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }

    const fig = await resp.json();
    Plotly.newPlot(divId, fig.data, fig.layout, { responsive: true });
  } catch (err) {
    console.error("Failed to load chart:", err);
    container.innerHTML =
      '<div class="chart-loading text-red-500">' +
      '<p>Failed to load chart. Please try refreshing the page.</p>' +
      "</div>";
  }
}

/**
 * Render a comparison chart (multi-run overlay) from an API endpoint.
 *
 * @param {string} divId - The DOM element ID for the chart container.
 * @param {string} endpointUrl - The API URL that returns comparison figure JSON.
 */
async function renderCompareChart(divId, endpointUrl) {
  const container = document.getElementById(divId);
  if (!container) {
    console.error("Chart container not found:", divId);
    return;
  }

  try {
    const resp = await fetch(endpointUrl, {
      credentials: "same-origin",
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }

    const fig = await resp.json();
    Plotly.newPlot(divId, fig.data, fig.layout, { responsive: true });
  } catch (err) {
    console.error("Failed to load comparison chart:", err);
    container.innerHTML =
      '<div class="chart-loading text-red-500">' +
      '<p>Failed to load comparison chart. Please try refreshing the page.</p>' +
      "</div>";
  }
}
