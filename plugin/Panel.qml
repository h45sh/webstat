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

  function refresh() {
    if (hostWidget && hostWidget.refresh) hostWidget.refresh()
  }

  function openSite(url) {
    openProc.command = ["xdg-open", url]
    openProc.running = true
  }

  function removeSite(target) {
    removeProc.command = ["webstat", "remove", target]
    removeProc.running = true
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

  Process {
    id: openProc
  }

  Process {
    id: removeProc
    onExited: root.refresh()
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
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

          PanelHero {
            title: "Webstat Monitor"
            foreground: root.fg
            fontFamily: root.fontFamily
            detail: root.sites.length > 0 ? (root.pendingCount > 0 ? root.pendingCount + " offline" : "All online") : "Idle"
            meta: root.sites.length + " website(s) in watchlist"
            iconComponent: Text {
              textFormat: Text.PlainText
              text: "󰖟"
              color: root.pendingCount > 0 ? (root.bar ? root.bar.urgent : Color.urgent) : root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
            }
          }

          Text {
            visible: root.sites.length === 0
            textFormat: Text.PlainText
            width: parent.width
            text: "No websites being monitored.\n\nAdd one from the terminal:\n  webstat add <url> --open\n  webstat watch <url>"
            color: root.fg
            opacity: 0.6
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            horizontalAlignment: Text.AlignHCenter
          }

          Repeater {
            model: root.sites

            Column {
              id: siteRow
              required property var modelData
              width: column.width
              spacing: Style.space(6)

              PanelSeparator { foreground: root.fg }

              Item {
                width: parent.width
                implicitHeight: Math.max(labels.implicitHeight, actionButtons.implicitHeight)

                Column {
                  id: labels
                  anchors.left: parent.left
                  anchors.right: actionButtons.left
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(2)

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

                  Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    elide: Text.ElideRight
                    text: Model.statusBadge(siteRow.modelData.status) + "  ·  " + Model.formatLatency(siteRow.modelData.latency_ms)
                    color: siteRow.modelData.is_up ? (root.bar ? root.bar.accent : Color.accent) : (root.bar ? root.bar.urgent : Color.urgent)
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
                    text: "Open"
                    fontSize: Style.font.caption
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    bordered: true
                    onClicked: root.openSite(siteRow.modelData.url)
                  }

                  Button {
                    text: "✕"
                    fontSize: Style.font.caption
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    bordered: true
                    onClicked: root.removeSite(siteRow.modelData.id)
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
