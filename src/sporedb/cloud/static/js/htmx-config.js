/**
 * SporeDB Dashboard - HTMX configuration and event handlers.
 *
 * Handles session expiry redirects, error toasts, and 401/403
 * responses from HTMX requests.
 */

document.addEventListener("DOMContentLoaded", function () {
  /**
   * Handle 303 redirects for expired sessions.
   * When HTMX receives a 303 response (from cookie auth redirect),
   * perform a full-page redirect to the login page.
   */
  document.body.addEventListener("htmx:beforeSwap", function (evt) {
    var status = evt.detail.xhr.status;

    // 401 or 403 -- redirect to login
    if (status === 401 || status === 403) {
      window.location.href = "/dash/login?next=" + encodeURIComponent(window.location.pathname);
      evt.detail.shouldSwap = false;
      return;
    }

    // 303 redirect -- follow it as a full page navigation
    if (status === 303) {
      var location = evt.detail.xhr.getResponseHeader("Location");
      if (location) {
        window.location.href = location;
        evt.detail.shouldSwap = false;
        return;
      }
    }
  });

  /**
   * Show toast notification on server errors (5xx).
   */
  document.body.addEventListener("htmx:responseError", function (evt) {
    var status = evt.detail.xhr ? evt.detail.xhr.status : 0;
    var toastContainer = document.getElementById("toast-container");
    if (!toastContainer) return;

    var message = "An error occurred. Please try again.";
    if (status >= 500) {
      message = "Server error (" + status + "). Please try again later.";
    }

    toastContainer.innerHTML =
      '<div class="px-4 py-2 rounded shadow-lg text-white text-sm bg-red-500" ' +
      'style="animation: fadeIn 0.3s ease-in">' +
      message +
      "</div>";

    // Auto-dismiss after 3 seconds
    setTimeout(function () {
      toastContainer.innerHTML = "";
    }, 3000);
  });
});
