(function () {
  var primary = localStorage.getItem("primary");
  if (!primary || primary.toLowerCase() === "#006666" || primary === "#1D5B79") {
    primary = "#C44ECC";
    localStorage.setItem("primary", primary);
  }
  var secondary = localStorage.getItem("secondary");
  if (!secondary || secondary.toLowerCase() === "#fe6a49" || secondary === "#468B97") {
    secondary = "#603CD8";
    localStorage.setItem("secondary", secondary);
  }

  window.RihoAdminConfig = {
    // Theme Primary Color: RGB(196, 78, 204)
    primary: primary,
    // Theme Secondary Color: RGB(96, 60, 216)
    secondary: secondary,
  };
})();
