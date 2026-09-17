// CODE DECK menu bar app.
//
// A status item with a live readout (spend · quota, blue when a session needs
// you) whose popover is the real dashboard: a WKWebView on the server's
// /player route — the same React frame the USB screen shows, over the same
// WebSocket. Click pins the popover open; hovering peeks it. No dependencies;
// built with swiftc by build.sh.

import Carbon.HIToolbox
import Cocoa
import WebKit

let serverURL = URL(string: ProcessInfo.processInfo.environment["CODE_DECK_URL"] ?? "http://127.0.0.1:8765")!
let launchAgentLabel = "com.codedeck.menubar"
let attention = NSColor(srgbRed: 0x4a / 255, green: 0xa3 / 255, blue: 0xff / 255, alpha: 1)
let muted = NSColor.secondaryLabelColor

// MARK: - State summary pulled from /api/state

struct Summary {
    var ok = false
    var costUSD = 0.0
    var codexQuota: Double? = nil
    var maxQuota: Double? = nil
    var needsYou = false
    var turnEnded = false
    var liveSessions = 0
    var deviceConnected = false
    var lastPushMs: Int? = nil
    var renderer = ""

    static func parse(_ data: Data) -> Summary {
        var s = Summary()
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return s }
        s.ok = true
        for tool in root["tools"] as? [[String: Any]] ?? [] {
            let name = tool["name"] as? String ?? ""
            if name == "Claude Code" { s.costUSD = tool["cost_usd"] as? Double ?? 0 }
            if name == "Codex" { s.codexQuota = tool["quota_pct"] as? Double }
            if name == "Claude Max" { s.maxQuota = tool["quota_pct"] as? Double }
            for sess in tool["sessions"] as? [[String: Any]] ?? [] {
                if sess["live"] as? Bool == true { s.liveSessions += 1 }
                if sess["needs_input"] as? Bool == true {
                    if sess["attention_kind"] as? String == "idle" { s.turnEnded = true } else { s.needsYou = true }
                }
            }
        }
        if let dev = root["device"] as? [String: Any] {
            s.deviceConnected = dev["connected"] as? Bool ?? false
            s.lastPushMs = dev["last_push_ms"] as? Int
            s.renderer = dev["renderer"] as? String ?? ""
        }
        return s
    }
}

// MARK: - Popover content: the live player

final class PlayerViewController: NSViewController, WKNavigationDelegate {
    let webView: WKWebView
    let offline = NSTextField(labelWithString: "CODE DECK server is offline\nstart it with `code-deck service install`")
    var zoom: CGFloat = 1.0 { didSet { apply() } }
    private var retry: Timer?

    init() {
        let cfg = WKWebViewConfiguration()
        cfg.suppressesIncrementalRendering = true
        webView = WKWebView(frame: .zero, configuration: cfg)
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError() }

    override func loadView() {
        let v = NSView(frame: NSRect(x: 0, y: 0, width: 320, height: 480))
        v.wantsLayer = true
        v.layer?.backgroundColor = NSColor(srgbRed: 0x1a / 255, green: 0x1a / 255, blue: 0x19 / 255, alpha: 1).cgColor
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        webView.autoresizingMask = [.width, .height]
        v.addSubview(webView)
        offline.alignment = .center
        offline.textColor = muted
        offline.font = .systemFont(ofSize: 12)
        offline.maximumNumberOfLines = 3
        offline.isHidden = true
        offline.autoresizingMask = [.width, .minYMargin, .maxYMargin]
        v.addSubview(offline)
        view = v
        apply()
        load()
    }

    func apply() {
        let size = NSSize(width: 320 * zoom, height: 480 * zoom)
        preferredContentSize = size
        view.frame = NSRect(origin: .zero, size: size)
        webView.frame = view.bounds
        offline.frame = NSRect(x: 16, y: size.height / 2 - 24, width: size.width - 32, height: 48)
        if #available(macOS 11.0, *) { webView.pageZoom = zoom }
    }

    func load() {
        webView.load(URLRequest(url: serverURL.appendingPathComponent("player"), cachePolicy: .reloadIgnoringLocalCacheData))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        offline.isHidden = true
        webView.isHidden = false
        retry?.invalidate(); retry = nil
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { failed() }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { failed() }

    private func failed() {
        webView.isHidden = true
        offline.isHidden = false
        retry?.invalidate()
        retry = Timer.scheduledTimer(withTimeInterval: 5, repeats: false) { [weak self] _ in self?.load() }
    }
}

// MARK: - Floating always-on-top dashboard window (for full menu bars, ⌥⇧D)

final class FloatingPanel: NSPanel {
    let player = PlayerViewController()

    init(zoom: CGFloat) {
        let size = NSSize(width: 320 * zoom, height: 480 * zoom)
        super.init(contentRect: NSRect(origin: .zero, size: size),
                   styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        level = .floating
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        isMovableByWindowBackground = true
        hidesOnDeactivate = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isReleasedWhenClosed = false
        player.zoom = zoom
        player.view.wantsLayer = true
        player.view.layer?.cornerRadius = 12
        player.view.layer?.masksToBounds = true
        contentViewController = player
        setFrameAutosaveName("codedeck-float")
        if !setFrameUsingName("codedeck-float"), let screen = NSScreen.main {
            let v = screen.visibleFrame   // default: top-right, under the menu bar
            setFrameOrigin(NSPoint(x: v.maxX - size.width - 16, y: v.maxY - size.height - 16))
        }
    }
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { orderOut(nil) }   // Esc closes
    override func keyDown(with event: NSEvent) {
        if event.keyCode == UInt16(kVK_Escape) { orderOut(nil) } else { super.keyDown(with: event) }
    }
}

// MARK: - Status item + popover controller

// NSResponder so the status button's tracking area can deliver
// mouseEntered/mouseExited here (hover peek).
final class StatusController: NSResponder, NSMenuDelegate {
    required init?(coder: NSCoder) { fatalError() }
    static weak var shared: StatusController?
    let item: NSStatusItem
    let popover = NSPopover()
    let player = PlayerViewController()
    let defaults = UserDefaults.standard
    private var floating: FloatingPanel?
    private var hotKey: EventHotKeyRef?

    private var pinned = false
    private var hoverTimer: Timer?
    private var leaveTimer: Timer?
    private var pollTimer: Timer?
    private var outsideMonitor: Any?
    private var summary = Summary()

    var hoverEnabled: Bool { defaults.object(forKey: "hover") as? Bool ?? true }
    var readoutEnabled: Bool { defaults.object(forKey: "readout") as? Bool ?? true }
    var zoom: CGFloat { CGFloat(defaults.object(forKey: "zoom") as? Double ?? 1.0) }

    override init() {
        // Full menu bars hide the leftmost third-party items (by the notch), so
        // on first launch ask to sit rightmost among them. macOS reads the
        // preferred position from defaults before the item is created.
        let posKey = "NSStatusItem Preferred Position codedeck"
        if UserDefaults.standard.object(forKey: posKey) == nil { UserDefaults.standard.set(0, forKey: posKey) }
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.autosaveName = "codedeck"
        super.init()
        StatusController.shared = self
        registerHotKey()
        popover.contentViewController = player
        popover.behavior = .applicationDefined
        popover.animates = true
        popover.appearance = NSAppearance(named: .darkAqua)
        player.zoom = zoom

        if let button = item.button {
            button.image = NSImage(systemSymbolName: "rectangle.portrait.inset.filled", accessibilityDescription: "CODE DECK")
            button.image?.isTemplate = true
            button.imagePosition = .imageLeading
            button.target = self
            button.action = #selector(clicked(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
            let area = NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                      owner: self, userInfo: nil)
            button.addTrackingArea(area)
        }
        render()
        poll()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
    }

    // -- readout ------------------------------------------------------------
    private func poll() {
        var req = URLRequest(url: serverURL.appendingPathComponent("api/state"), timeoutInterval: 3)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: req) { [weak self] data, _, _ in
            let s = data.map(Summary.parse) ?? Summary()
            DispatchQueue.main.async { self?.summary = s; self?.render() }
        }.resume()
    }

    private func render() {
        guard let button = item.button else { return }
        let s = summary
        let title = NSMutableAttributedString()
        let font = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium)
        if s.needsYou || s.turnEnded {
            title.append(NSAttributedString(string: "● ", attributes: [
                .foregroundColor: s.needsYou ? attention : muted, .font: font, .baselineOffset: 0]))
        }
        if readoutEnabled && s.ok {
            var parts = [String(format: "$%.0f", s.costUSD)]
            if let q = s.codexQuota { parts.append(String(format: "%.0f%%", q)) }
            title.append(NSAttributedString(string: parts.joined(separator: " · "),
                                            attributes: [.font: font, .foregroundColor: NSColor.labelColor]))
        } else if !s.ok {
            title.append(NSAttributedString(string: "offline", attributes: [.font: font, .foregroundColor: muted]))
        }
        button.attributedTitle = title
        button.toolTip = s.ok
            ? "CODE DECK · \(s.liveSessions) live · device \(s.deviceConnected ? "connected" : "absent")"
              + (s.lastPushMs.map { " · last push \($0) ms" } ?? "")
            : "CODE DECK · server offline"
        // a needs-you re-render keeps the popover fresh if it is showing
        if popover.isShown && s.needsYou { player.webView.evaluateJavaScript("window.__cd && (window.__cd.dirty++)", completionHandler: nil) }
    }

    // -- interaction --------------------------------------------------------
    @objc private func clicked(_ sender: Any?) {
        if NSApp.currentEvent?.type == .rightMouseUp { showMenu(); return }
        if popover.isShown && pinned { close() } else { show(pinned: true) }
    }

    override func mouseEntered(with event: NSEvent) {
        guard hoverEnabled, !popover.isShown else { return }
        hoverTimer?.invalidate()
        hoverTimer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: false) { [weak self] _ in self?.show(pinned: false) }
    }

    override func mouseExited(with event: NSEvent) {
        hoverTimer?.invalidate()
        scheduleLeaveCheck()
    }

    private func show(pinned pin: Bool) {
        guard let button = item.button else { return }
        pinned = pin || pinned
        if !popover.isShown {
            player.zoom = zoom
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            outsideMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
                self?.close()   // click anywhere outside the app closes it
            }
        }
        if !pinned { scheduleLeaveCheck() }
    }

    private func scheduleLeaveCheck() {
        leaveTimer?.invalidate()
        leaveTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] t in
            guard let self, self.popover.isShown, !self.pinned else { t.invalidate(); return }
            if !self.mouseIsOverUs() { self.close() }
        }
    }

    private func mouseIsOverUs() -> Bool {
        let p = NSEvent.mouseLocation
        var frames: [NSRect] = []
        if let w = item.button?.window { frames.append(w.frame.insetBy(dx: -4, dy: -4)) }
        if let w = popover.contentViewController?.view.window { frames.append(w.frame.insetBy(dx: -8, dy: -8)) }
        return frames.contains { $0.contains(p) }
    }

    private func close() {
        pinned = false
        leaveTimer?.invalidate()
        if let m = outsideMonitor { NSEvent.removeMonitor(m); outsideMonitor = nil }
        popover.performClose(nil)
    }

    // -- floating window + global hotkey ------------------------------------
    // Carbon hot keys work without the Accessibility permission a global
    // NSEvent key monitor would need.
    private func registerHotKey() {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ -> OSStatus in
            DispatchQueue.main.async { StatusController.shared?.toggleFloating() }
            return noErr
        }, 1, &spec, nil, nil)
        let id = EventHotKeyID(signature: 0x43444B31, id: 1)   // 'CDK1'
        RegisterEventHotKey(UInt32(kVK_ANSI_D), UInt32(optionKey | shiftKey), id,
                            GetApplicationEventTarget(), 0, &hotKey)
    }

    @objc func toggleFloating() {
        if let f = floating, f.isVisible { f.orderOut(nil); return }
        if floating == nil || floating!.player.zoom != zoom {
            floating?.orderOut(nil)
            floating = FloatingPanel(zoom: zoom)
        }
        close()
        floating?.orderFrontRegardless()
    }

    // -- menu ---------------------------------------------------------------
    private func showMenu() {
        let menu = NSMenu()
        let float = menu.addItem(withTitle: floating?.isVisible == true ? "Hide floating dashboard" : "Show floating dashboard",
                                 action: #selector(toggleFloating), keyEquivalent: "D")
        float.keyEquivalentModifierMask = [.option, .shift]
        float.target = self
        menu.addItem(withTitle: "Open builder", action: #selector(openBuilder), keyEquivalent: "b").target = self
        menu.addItem(withTitle: "Open player in browser", action: #selector(openPlayer), keyEquivalent: "").target = self
        menu.addItem(.separator())
        let hover = menu.addItem(withTitle: "Show on hover", action: #selector(toggleHover), keyEquivalent: "")
        hover.target = self; hover.state = hoverEnabled ? .on : .off
        let readout = menu.addItem(withTitle: "Show spend · quota in menu bar", action: #selector(toggleReadout), keyEquivalent: "")
        readout.target = self; readout.state = readoutEnabled ? .on : .off
        let size = NSMenuItem(title: "Popover size", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        for z in [1.0, 1.5, 2.0] {
            let it = sub.addItem(withTitle: z == 1 ? "1×" : String(format: "%.1f×", z), action: #selector(setZoom(_:)), keyEquivalent: "")
            it.target = self; it.representedObject = z; it.state = abs(Double(zoom) - z) < 0.01 ? .on : .off
        }
        size.submenu = sub
        menu.addItem(size)
        let login = menu.addItem(withTitle: "Launch at login", action: #selector(toggleLogin), keyEquivalent: "")
        login.target = self; login.state = FileManager.default.fileExists(atPath: launchAgentPath) ? .on : .off
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit CODE DECK menu bar", action: #selector(quit), keyEquivalent: "q").target = self
        close()
        if let button = item.button { menu.popUp(positioning: nil, at: NSPoint(x: 0, y: button.bounds.height + 4), in: button) }
    }

    @objc private func openBuilder() { NSWorkspace.shared.open(serverURL) }
    @objc private func openPlayer() { NSWorkspace.shared.open(serverURL.appendingPathComponent("player")) }
    @objc private func toggleHover() { defaults.set(!hoverEnabled, forKey: "hover") }
    @objc private func toggleReadout() { defaults.set(!readoutEnabled, forKey: "readout"); render() }
    @objc private func setZoom(_ sender: NSMenuItem) {
        defaults.set(sender.representedObject as? Double ?? 1.0, forKey: "zoom")
        player.zoom = zoom
    }
    @objc private func quit() { NSApp.terminate(nil) }

    // Launch at login = a LaunchAgent pointing at this binary (works for an
    // ad-hoc-signed app outside the App Store; SMAppService needs a bundle
    // in a registered location).
    private var launchAgentPath: String {
        NSString(string: "~/Library/LaunchAgents/\(launchAgentLabel).plist").expandingTildeInPath
    }
    @objc private func toggleLogin() {
        let path = launchAgentPath
        let domain = "gui/\(getuid())"
        if FileManager.default.fileExists(atPath: path) {
            run("/bin/launchctl", ["bootout", "\(domain)/\(launchAgentLabel)"])
            try? FileManager.default.removeItem(atPath: path)
        } else {
            let plist: [String: Any] = [
                "Label": launchAgentLabel,
                "ProgramArguments": [Bundle.main.executablePath ?? ""],
                "RunAtLoad": true,
                "KeepAlive": ["SuccessfulExit": false],
                "ProcessType": "Interactive",
            ]
            if let data = try? PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0) {
                try? FileManager.default.createDirectory(atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
                FileManager.default.createFile(atPath: path, contents: data)
                run("/bin/launchctl", ["bootstrap", domain, path])
            }
        }
    }
    private func run(_ exe: String, _ args: [String]) {
        let p = Process(); p.executableURL = URL(fileURLWithPath: exe); p.arguments = args
        try? p.run(); p.waitUntilExit()
    }
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate {
    var status: StatusController?
    func applicationDidFinishLaunching(_ notification: Notification) {
        status = StatusController()
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // menu bar only, no Dock icon
let delegate = AppDelegate()
app.delegate = delegate
app.run()
