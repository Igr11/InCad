import PDFKit
let a = CommandLine.arguments
let out = PDFDocument()
for path in a[2...] {
    let d = PDFDocument(url: URL(fileURLWithPath: path))!
    for i in 0..<d.pageCount { out.insert(d.page(at: i)!, at: out.pageCount) }
}
out.documentAttributes = [PDFDocumentAttribute.titleAttribute: ProcessInfo.processInfo.environment["PDF_TITLE"] ?? "InCad"]
out.write(to: URL(fileURLWithPath: a[1]))
print("pages", out.pageCount)
