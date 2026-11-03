.pragma library

// Helper functions for Webstat Omarchy plugin

function parseSites(text) {
  try {
    var data = JSON.parse(String(text || "").trim())
    if (Array.isArray(data)) {
      return data
    }
  } catch (e) {}
  return []
}

function parseCheckResult(text) {
  try {
    var data = JSON.parse(String(text || "").trim())
    if (data && typeof data === "object" && data.url) {
      return data
    }
  } catch (e) {}
  return null
}

function countPending(sites) {
  if (!Array.isArray(sites)) return 0
  var count = 0
  for (var i = 0; i < sites.length; i++) {
    if (!sites[i].is_up) {
      count++
    }
  }
  return count
}

function formatLatency(ms) {
  if (ms === null || ms === undefined) return "—"
  return Math.round(ms) + " ms"
}

// High-contrast, theme-agnostic vibrant colors for status visibility
function statusColor(status, isUp) {
  if (status === "ONLINE" || isUp) return "#4ade80" // Bright emerald green
  if (status === "REDIRECT") return "#38bdf8" // Bright sky blue
  if (status === "CLIENT_ERROR") return "#fbbf24" // Bright amber
  if (status === "SERVER_ERROR") return "#f87171" // Bright coral red
  if (status === "UNREACHABLE") return "#ef4444" // Vivid red
  return "#94a3b8" // Slate gray
}

function statusBadge(status, code) {
  var codeStr = code ? " (" + code + ")" : ""
  if (status === "ONLINE") return "● ONLINE" + codeStr
  if (status === "REDIRECT") return "↗ REDIRECT" + codeStr
  if (status === "CLIENT_ERROR") return "▲ CLIENT ERROR" + codeStr
  if (status === "SERVER_ERROR") return "✖ SERVER ERROR" + codeStr
  if (status === "UNREACHABLE") return "✖ UNREACHABLE"
  return "? PENDING"
}
