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

function statusBadge(status) {
  if (status === "ONLINE") return "● ONLINE"
  if (status === "REDIRECT") return "↗ REDIRECT"
  if (status === "CLIENT_ERROR") return "▲ CLIENT ERR"
  if (status === "SERVER_ERROR") return "✖ SERVER ERR"
  if (status === "UNREACHABLE") return "✖ DOWN"
  return "? PENDING"
}
