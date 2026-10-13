import AppKit
import WebKit
import PDFKit

let args = CommandLine.arguments
let dir = URL(fileURLWithPath: args[1])
let out = URL(fileURLWithPath: args[2])
let pages = try! FileManager.default.contentsOfDirectory(atPath: dir.path).filter { $0.hasSuffix(".html") }.sorted()

class Renderer: NSObject, WKNavigationDelegate {
    let web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1920, height: 1080))
    var index = 0
    let doc = PDFDocument()
    override init() { super.init(); web.navigationDelegate = self }
    func next() {
        if index >= pages.count {
            doc.write(to: out)
            print("WROTE", doc.pageCount, "pages")
            NSApp.terminate(nil)
            return
        }
        let url = dir.appendingPathComponent(pages[index])
        web.loadFileURL(url, allowingReadAccessTo: dir)
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // web fonts: wait until document.fonts is ready, then a moment for layout
        webView.evaluateJavaScript("document.fonts.ready.then(() => document.fonts.size)") { _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
                let cfg = WKPDFConfiguration()
                cfg.rect = CGRect(x: 0, y: 0, width: 1920, height: 1080)
                webView.createPDF(configuration: cfg) { result in
                    if case .success(let data) = result, let page = PDFDocument(data: data)?.page(at: 0) {
                        self.doc.insert(page, at: self.doc.pageCount)
                        print("page", pages[self.index])
                    } else {
                        print("FAILED", pages[self.index])
                    }
                    self.index += 1
                    self.next()
                }
            }
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let r = Renderer()
DispatchQueue.main.async { r.next() }
app.run()
