import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "h45sh.webstat"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root
  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  readonly property var sites: hostWidget ? hostWidget.sites : []
  readonly property int pendingCount: Model.countPending(sites)

  property var checkResult: null
  property bool checking: false
  property bool adding: false
  property bool refreshing: false
  property string checkingSiteId: ""

  function refresh() {
    if (hostWidget && hostWidget.refresh) hostWidget.refresh()
  }

  function openSite(url) {
    openProc.command = ["xdg-open", url]
    openProc.running = true
  }

  function removeSite(targetId) {
    // Optimistic UI: remove immediately from view without waiting
    var filtered = []
    for (var i = 0; i < root.sites.length; i++) {
      if (root.sites[i].id !== targetId) filtered.push(root.sites[i])
    }
    if (hostWidget) hostWidget.sites = filtered

    removeProc.command = ["webstat", "remove", "--", targetId]
    removeProc.running = true
  }

  function checkSingleSite(siteId, url) {
    root.checkingSiteId = siteId
    singleCheckProc.command = ["webstat", "check", "--", url]
    singleCheckProc.running = true
  }

  function addCurrentUrl() {
    var raw = String(urlField.text || "").trim()
    if (!raw) return
    root.adding = true
    var args = ["webstat", "add"]
    if (autoOpenSwitch.checked) args.push("--open")
    if (keepWatchingSwitch.checked) args.push("--keep")
    args.push("--")
    args.push(raw)
    addProc.command = args
    addProc.running = true
    urlField.text = ""
  }

  function checkCurrentUrl() {
    var raw = String(urlField.text || "").trim()
    if (!raw) return
    root.checking = true
    root.checkResult = null
    checkProc.command = ["webstat", "check", "--json", "--", raw]
    checkProc.running = true
  }

  function refreshAll() {
    root.refreshing = true
    refreshProc.running = true
  }

  function clearWatchlist() {
    if (hostWidget) hostWidget.sites = []
    root.checkResult = null
    clearProc.running = true
  }

  function open() {
    refresh()
    root.controller.show()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  Process { id: openProc }

  Process {
    id: removeProc
    onExited: root.refresh()
  }

  Process {
    id: addProc
    onExited: {
      root.adding = false
      root.refresh()
    }
  }

  Process {
    id: singleCheckProc
    onExited: {
      root.checkingSiteId = ""
      root.refresh()
    }
  }

  Process {
    id: checkProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        root.checking = false
        root.checkResult = Model.parseCheckResult(text)
      }
    }
  }

  Process {
    id: refreshProc
    command: ["webstat", "refresh"]
    onExited: {
      root.refreshing = false
      root.refresh()
    }
  }

  Process {
    id: clearProc
    command: ["webstat", "clear"]
    onExited: root.refresh()
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(480))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: column
          width: scroll.width
          spacing: Style.space(12)

          // Header Hero
          PanelHero {
            title: "Webstat Monitor"
            foreground: root.fg
            fontFamily: root.fontFamily
            detail: root.sites.length > 0 ? (root.pendingCount > 0 ? root.pendingCount + " offline" : "All online") : "Idle"
            meta: root.sites.length + " website(s) in watchlist"
            iconComponent: Text {
              textFormat: Text.PlainText
              text: "󰖟"
              color: root.pendingCount > 0 ? "#ef4444" : "#38bdf8"
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
            }
          }

          // Top Header Action Row (Refresh All + Clear)
          Row {
            width: parent.width
            spacing: Style.space(8)

            Button {
              text: root.refreshing ? "Refreshing…" : "↻ Refresh All"
              fontSize: Style.font.caption
              foreground: root.fg
              fontFamily: root.fontFamily
              bordered: true
              active: root.refreshing
              onClicked: root.refreshAll()
            }

            Button {
              text: "🗑 Clear All"
              fontSize: Style.font.caption
              foreground: root.fg
              fontFamily: root.fontFamily
              bordered: true
              visible: root.sites.length > 0
              onClicked: root.clearWatchlist()
            }
          }

          PanelSeparator { foreground: root.fg }

          // Section 1: Add or Quick Check Form
          PanelSectionHeader {
            text: "Add or Quick Check Website"
            foreground: root.fg
            fontFamily: root.fontFamily
          }

          // Input Row with Add and Check Buttons
          Row {
            width: parent.width
            spacing: Style.space(8)

            TextField {
              id: urlField
              width: parent.width - addBtn.width - checkBtn.width - Style.space(16)
              placeholderText: "Enter website or domain (e.g. github.com)…"
              foreground: root.fg
              onAccepted: root.addCurrentUrl()
            }

            Button {
              id: addBtn
              text: root.adding ? "Adding…" : "Add"
              fontSize: Style.font.bodySmall
              foreground: "#38bdf8"
              fontFamily: root.fontFamily
              bordered: true
              active: root.adding
              onClicked: root.addCurrentUrl()
            }

            Button {
              id: checkBtn
              text: root.checking ? "Checking…" : "Check"
              fontSize: Style.font.bodySmall
              foreground: root.fg
              fontFamily: root.fontFamily
              bordered: true
              active: root.checking
              onClicked: root.checkCurrentUrl()
            }
          }

          // Options Row (Auto-Open & Keep Watching switches)
          Row {
            width: parent.width
            spacing: Style.space(16)

            Row {
              spacing: Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              ToggleSwitch {
                id: autoOpenSwitch
                checked: true
                anchors.verticalCenter: parent.verticalCenter
                onToggled: checked = !checked
              }
              Text {
                textFormat: Text.PlainText
                text: "Open browser when UP"
                color: root.fg
                opacity: 0.9
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            Row {
              spacing: Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              ToggleSwitch {
                id: keepWatchingSwitch
                checked: false
                anchors.verticalCenter: parent.verticalCenter
                onToggled: checked = !checked
              }
              Text {
                textFormat: Text.PlainText
                text: "Keep continuous watch"
                color: root.fg
                opacity: 0.9
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.verticalCenter: parent.verticalCenter
              }
            }
          }

          // Live Check Result Card
          BorderSurface {
            visible: root.checkResult !== null
            width: parent.width
            color: Style.controlFill(false, false, root.fg, Color.accent)
            radius: Style.cornerRadius
            borderSpec: Border.controlSpec("normal", root.checkResult && root.checkResult.is_up ? "#4ade80" : "#ef4444", Color.accent)
            implicitHeight: resultCol.implicitHeight + Style.space(16)

            Column {
              id: resultCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.space(10)
              spacing: Style.space(6)

              Row {
                width: parent.width
                spacing: Style.space(10)
                Text {
                  textFormat: Text.PlainText
                  text: root.checkResult ? Model.statusBadge(root.checkResult.status, root.checkResult.status_code) : ""
                  color: root.checkResult ? Model.statusColor(root.checkResult.status, root.checkResult.is_up) : root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                }
                Text {
                  textFormat: Text.PlainText
                  text: root.checkResult ? Model.formatLatency(root.checkResult.latency_ms) : ""
                  color: "#38bdf8"
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }
              }

              Text {
                textFormat: Text.PlainText
                text: root.checkResult ? root.checkResult.url : ""
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
                elide: Text.ElideRight
                width: parent.width
              }

              Text {
                visible: root.checkResult && root.checkResult.ssl_expires_days !== null
                textFormat: Text.PlainText
                text: root.checkResult && root.checkResult.ssl_expires_days !== null ? "SSL Certificate: " + root.checkResult.ssl_expires_days + " days remaining" : ""
                color: root.checkResult && root.checkResult.ssl_expires_days < 7 ? "#fbbf24" : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.7)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Text {
                visible: root.checkResult && root.checkResult.error_message !== null
                textFormat: Text.PlainText
                text: root.checkResult && root.checkResult.error_message ? "Error: " + root.checkResult.error_message : ""
                color: "#f87171"
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
                width: parent.width
              }

              Row {
                spacing: Style.space(8)
                Button {
                  text: "+ Add to Watchlist"
                  fontSize: Style.font.caption
                  foreground: "#38bdf8"
                  fontFamily: root.fontFamily
                  bordered: true
                  onClicked: {
                      var args = ["webstat", "add"]
                      if (autoOpenSwitch.checked) args.push("--open")
                      if (keepWatchingSwitch.checked) args.push("--keep")
                      args.push("--")
                      args.push(root.checkResult.url)
                      addProc.command = args
                      addProc.running = true
                      root.checkResult = null
                  }
                }
                Button {
                  text: "Dismiss"
                  fontSize: Style.font.caption
                  foreground: root.fg
                  fontFamily: root.fontFamily
                  bordered: true
                  onClicked: root.checkResult = null
                }
              }
            }
          }

          PanelSeparator { foreground: root.fg }

          // Section 2: Watchlist Header
          PanelSectionHeader {
            text: "Watchlist (" + root.sites.length + ")"
            foreground: root.fg
            fontFamily: root.fontFamily
          }

          // Empty state
          Text {
            visible: root.sites.length === 0
            textFormat: Text.PlainText
            width: parent.width
            text: "No websites being monitored.\n\nEnter a website above and click 'Add' or run in terminal:\n  webstat add <url> --open"
            color: root.fg
            opacity: 0.7
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            horizontalAlignment: Text.AlignHCenter
          }

          // Sites list
          Repeater {
            model: root.sites

            Column {
              id: siteRow
              required property var modelData
              width: column.width
              spacing: Style.space(6)

              Item {
                width: parent.width
                implicitHeight: Math.max(labels.implicitHeight, actionButtons.implicitHeight)

                Column {
                  id: labels
                  anchors.left: parent.left
                  anchors.right: actionButtons.left
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(3)

                  // Primary site name
                  Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    elide: Text.ElideRight
                    text: siteRow.modelData.display_name
                    color: root.fg
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                  }

                  // High-visibility status & metrics row
                  Row {
                    spacing: Style.space(6)

                    // Vibrant Status Badge (Green / Red / Amber / Cyan)
                    Text {
                      textFormat: Text.PlainText
                      text: Model.statusBadge(siteRow.modelData.status, siteRow.modelData.status_code)
                      color: Model.statusColor(siteRow.modelData.status, siteRow.modelData.is_up)
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      font.bold: true
                    }

                    Text {
                      textFormat: Text.PlainText
                      text: "·"
                      color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.4)
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }

                    // Bright Latency
                    Text {
                      textFormat: Text.PlainText
                      text: Model.formatLatency(siteRow.modelData.latency_ms)
                      color: "#38bdf8"
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }

                    // Auto-open tag
                    Text {
                      visible: siteRow.modelData.auto_open === true
                      textFormat: Text.PlainText
                      text: "[Auto-open]"
                      color: "#a78bfa"
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }

                    // Retries tag if down
                    Text {
                      visible: siteRow.modelData.retries > 0
                      textFormat: Text.PlainText
                      text: "(" + siteRow.modelData.retries + " retries)"
                      color: "#fbbf24"
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                    }
                  }

                  // Error message if any
                  Text {
                    visible: siteRow.modelData.last_error !== null && siteRow.modelData.last_error !== ""
                    textFormat: Text.PlainText
                    width: parent.width
                    elide: Text.ElideRight
                    text: siteRow.modelData.last_error ? siteRow.modelData.last_error : ""
                    color: "#f87171"
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }

                Row {
                  id: actionButtons
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(6)

                  Button {
                    text: root.checkingSiteId === siteRow.modelData.id ? "…" : "Check"
                    fontSize: Style.font.caption
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    bordered: true
                    active: root.checkingSiteId === siteRow.modelData.id
                    tooltipText: "Re-check this site immediately"
                    onClicked: root.checkSingleSite(siteRow.modelData.id, siteRow.modelData.url)
                  }

                  Button {
                    text: "Open"
                    fontSize: Style.font.caption
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    bordered: true
                    tooltipText: "Open in browser"
                    onClicked: root.openSite(siteRow.modelData.url)
                  }

                  Button {
                    text: "✕"
                    fontSize: Style.font.caption
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    bordered: true
                    tooltipText: "Remove from watchlist"
                    onClicked: root.removeSite(siteRow.modelData.id)
                  }
                }
              }

              PanelSeparator { foreground: root.fg }
            }
          }
        }
      }
    }
  }
}
