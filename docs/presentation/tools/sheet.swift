import AppKit
import PDFKit
let a = CommandLine.arguments
let doc = PDFDocument(url: URL(fileURLWithPath: a[1]))!
let w: CGFloat = 640, h: CGFloat = 360, cols = 4
let rows = (doc.pageCount + cols - 1) / cols
let sheet = NSImage(size: NSSize(width: w * CGFloat(cols), height: h * CGFloat(rows)))
sheet.lockFocus()
NSColor.gray.setFill(); NSRect(origin: .zero, size: sheet.size).fill()
for i in 0..<doc.pageCount {
    let img = doc.page(at: i)!.thumbnail(of: NSSize(width: w - 8, height: h - 8), for: .mediaBox)
    let r = i / cols, c = i % cols
    img.draw(in: NSRect(x: CGFloat(c) * w + 4, y: sheet.size.height - CGFloat(r + 1) * h + 4, width: w - 8, height: h - 8))
}
sheet.unlockFocus()
let rep = NSBitmapImageRep(data: sheet.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[2]))
if a.count > 3 {  // one page at full size
    let p = doc.page(at: Int(a[3])!)!.thumbnail(of: NSSize(width: 1920, height: 1080), for: .mediaBox)
    let r2 = NSBitmapImageRep(data: p.tiffRepresentation!)!
    try! r2.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[4]))
}
print("ok")
