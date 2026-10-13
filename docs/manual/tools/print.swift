// Prints an HTML file to a paginated A4 PDF with WebKit (CSS page breaks apply): swift print.swift in.html out.pdf
import AppKit
import WebKit

let args = CommandLine.arguments
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])

class Printer: NSObject, WKNavigationDelegate {
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 794, height: 1123), styleMask: [.titled],
                          backing: .buffered, defer: false)
    let web = WKWebView(frame: NSRect(x: 0, y: 0, width: 794, height: 1123))
    override init() {
        super.init()
        web.navigationDelegate = self
        window.contentView = web
    }
    func start() { web.loadFileURL(input, allowingReadAccessTo: input.deletingLastPathComponent()) }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // fonts and images first, then a moment for layout
        webView.evaluateJavaScript("Promise.all([document.fonts.ready, ...Array.from(document.images).map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r }))]).then(() => 1)") { _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.print() }
        }
    }
    func print() {
        let info = NSPrintInfo()
        info.paperSize = NSSize(width: 595.28, height: 841.89)  // A4 in points
        info.topMargin = 0; info.bottomMargin = 0; info.leftMargin = 0; info.rightMargin = 0  // margins come from CSS @page
        info.horizontalPagination = .fit
        info.verticalPagination = .automatic
        info.isHorizontallyCentered = false
        info.isVerticallyCentered = false
        info.jobDisposition = .save
        info.dictionary()[NSPrintInfo.AttributeKey.jobSavingURL] = output
        let op = web.printOperation(with: info)
        op.showsPrintPanel = false
        op.showsProgressPanel = false
        op.view?.frame = web.bounds
        op.runModal(for: window, delegate: self, didRun: #selector(done(_:success:context:)), contextInfo: nil)
    }
    @objc func done(_ op: NSPrintOperation, success: Bool, context: UnsafeMutableRawPointer?) {
        Swift.print(success ? "WROTE \(output.path)" : "FAILED")
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let p = Printer()
DispatchQueue.main.async { p.start() }
app.run()
