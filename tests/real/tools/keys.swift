// keys <code> [<code> ...]  — real key presses by macOS virtual keycode; prefix S for Shift, C for Command,
// e.g. "S24" = Shift+'=' (gives '+'), "C12" = Cmd+Q.  36=Return 53=Esc 48=Tab 51=Delete 49=Space
import CoreGraphics
import Foundation
let src = CGEventSource(stateID: .hidSystemState)
for raw in CommandLine.arguments.dropFirst() {
    var s = Substring(raw)
    var flags = CGEventFlags()
    while let c = s.first, "SC".contains(c) {
        if c == "S" { flags.insert(.maskShift) }
        if c == "C" { flags.insert(.maskCommand) }
        s = s.dropFirst()
    }
    let k = CGKeyCode(UInt16(s)!)
    let down = CGEvent(keyboardEventSource: src, virtualKey: k, keyDown: true)!
    let up = CGEvent(keyboardEventSource: src, virtualKey: k, keyDown: false)!
    down.flags = flags; up.flags = flags
    down.post(tap: .cghidEventTap); usleep(40000); up.post(tap: .cghidEventTap); usleep(80000)
}
