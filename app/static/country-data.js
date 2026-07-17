(function () {
  const COUNTRY_CODES = {
    fr: "France",
    gb: "United Kingdom",
    es: "Spain",
    it: "Italy",
    pt: "Portugal",
    de: "Germany",
    nl: "Netherlands",
    be: "Belgium",
    ch: "Switzerland",
    at: "Austria",
    gr: "Greece",
    ie: "Ireland",
    jp: "Japan",
    us: "United States",
    ca: "Canada",
    au: "Australia",
    th: "Thailand",
    my: "Malaysia",
    vn: "Vietnam",
    id: "Indonesia",
    sg: "Singapore",
    kh: "Cambodia",
  };

  const NAME_TO_CODE = {};
  Object.entries(COUNTRY_CODES).forEach(([code, name]) => {
    NAME_TO_CODE[name.toLowerCase()] = code;
  });
  NAME_TO_CODE.uk = "gb";
  NAME_TO_CODE.england = "gb";
  NAME_TO_CODE.scotland = "gb";
  NAME_TO_CODE.usa = "us";
  NAME_TO_CODE["viet nam"] = "vn";

  const CITY_HINTS = [
    ["france", "France", "fr"],
    ["paris", "France", "fr"],
    ["lyon", "France", "fr"],
    ["spain", "Spain", "es"],
    ["barcelona", "Spain", "es"],
    ["madrid", "Spain", "es"],
    ["italy", "Italy", "it"],
    ["rome", "Italy", "it"],
    ["milan", "Italy", "it"],
    ["portugal", "Portugal", "pt"],
    ["lisbon", "Portugal", "pt"],
    ["germany", "Germany", "de"],
    ["berlin", "Germany", "de"],
    ["munich", "Germany", "de"],
    ["netherlands", "Netherlands", "nl"],
    ["amsterdam", "Netherlands", "nl"],
    ["japan", "Japan", "jp"],
    ["tokyo", "Japan", "jp"],
    ["kyoto", "Japan", "jp"],
    ["united states", "United States", "us"],
    ["new york", "United States", "us"],
    ["canada", "Canada", "ca"],
    ["toronto", "Canada", "ca"],
    ["australia", "Australia", "au"],
    ["sydney", "Australia", "au"],
    ["thailand", "Thailand", "th"],
    ["bangkok", "Thailand", "th"],
    ["phuket", "Thailand", "th"],
    ["chiang mai", "Thailand", "th"],
    ["koh tao", "Thailand", "th"],
    ["malaysia", "Malaysia", "my"],
    ["kuala lumpur", "Malaysia", "my"],
    ["malacca", "Malaysia", "my"],
    ["melaka", "Malaysia", "my"],
    ["penang", "Malaysia", "my"],
    ["vietnam", "Vietnam", "vn"],
    ["hanoi", "Vietnam", "vn"],
    ["ho chi minh", "Vietnam", "vn"],
    ["hoa lu", "Vietnam", "vn"],
    ["hoa lư", "Vietnam", "vn"],
    ["da nang", "Vietnam", "vn"],
    ["hoi an", "Vietnam", "vn"],
    ["ninh binh", "Vietnam", "vn"],
    ["indonesia", "Indonesia", "id"],
    ["bali", "Indonesia", "id"],
    ["jakarta", "Indonesia", "id"],
    ["singapore", "Singapore", "sg"],
    ["cambodia", "Cambodia", "kh"],
    ["siem reap", "Cambodia", "kh"],
    ["united kingdom", "United Kingdom", "gb"],
    ["london", "United Kingdom", "gb"],
  ];

  function inferCountry(text) {
    const loc = (text || "").toLowerCase();
    if (!loc) return { name: "", code: "" };
    for (const [hint, name, code] of CITY_HINTS) {
      if (loc.includes(hint)) return { name, code };
    }
    const direct = NAME_TO_CODE[loc.trim()];
    if (direct) return { name: COUNTRY_CODES[direct], code: direct };
    return { name: "", code: "" };
  }

  function countryNameToCode(name) {
    const text = (name || "").trim().toLowerCase();
    if (!text) return "";
    if (NAME_TO_CODE[text]) return NAME_TO_CODE[text];
    for (const [label, code] of Object.entries(NAME_TO_CODE)) {
      if (label.length >= 5 && (label.includes(text) || text.includes(label))) return code;
    }
    return "";
  }

  function countryFlag(code) {
    if (!code || code.length !== 2) return "🌍";
    const pts = [...code.toUpperCase()].map((c) => 127397 + c.charCodeAt(0));
    return String.fromCodePoint(...pts);
  }

  window.gdpCountryData = {
    COUNTRY_CODES,
    CITY_HINTS,
    inferCountry,
    countryNameToCode,
    countryFlag,
  };
})();
