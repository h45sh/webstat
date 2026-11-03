import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "h45sh.webstat"

  readonly property string icon: "󰖟"
  property var sites: []
  readonly property int pendingCount: Model.countPending(sites)
  readonly property bool hasPending: pendingCount > 0

  function refresh() {
    stateFile.reload()
  }

  // Routing contract for Omarchy bar popouts
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false
  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    target.bar = root.bar
    target.settings = root.settings
    target.anchorItem = button
    target.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  // Instant reactive state reading via FileView and inotify (0ms latency, zero process spawning)
  FileView {
    id: stateFile
    path: Quickshell.env("HOME") + "/.local/state/webstat/sites.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.sites = Model.parseSites(text())
    onFileChanged: reload()
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical ? root.icon : (root.hasPending ? root.icon + " " + root.pendingCount : root.icon)
    fontSize: root.vertical ? Style.bar.iconFont : Style.font.body
    active: root.hasPending
    activeColor: "#ef4444"
    foreground: root.hasPending ? "#ef4444" : (root.bar ? root.bar.barForeground : Color.foreground)
    tooltipText: root.sites.length === 0
      ? "Webstat: No sites monitored"
      : (root.hasPending
          ? "Webstat: " + root.pendingCount + " site(s) offline / waiting"
          : "Webstat: All " + root.sites.length + " site(s) online")
    onPressed: function(b) {
      if (panelLoader.item) panelLoader.item.toggle()
    }
  }
}
