#!/usr/bin/env swift

import AppKit
import ApplicationServices
import Foundation

private let axSheetsAttribute = "AXSheets"

struct Options {
    var dryRun = false
    var singlePass = false
    var interval: TimeInterval = 0.7
    var promptForAccessibility = true
    let targetAppName = "Claude"
}

final class ClaudeAllowWatcher {
    private let options: Options
    private var lastClickAtBySignature: [String: Date] = [:]
    private let dedupeInterval: TimeInterval = 3.0

    init(options: Options) {
        self.options = options
    }

    func run() {
        waitForAccessibilityIfNeeded()
        log("accessibility ready")
        log("watching \(options.targetAppName) for permission buttons with priority: always-allow-project > always-allow > allow-once > allow")

        repeat {
            autoreleasepool {
                scanOnce()
            }
            if options.singlePass {
                break
            }
            Thread.sleep(forTimeInterval: options.interval)
        } while true
    }

    private func waitForAccessibilityIfNeeded() {
        var didPrompt = false

        while true {
            if AXIsProcessTrusted() {
                return
            }

            if options.promptForAccessibility && !didPrompt {
                let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
                let promptOptions = [key: true] as CFDictionary
                _ = AXIsProcessTrustedWithOptions(promptOptions)
                didPrompt = true
                log("accessibility permission is required. Grant access to this watcher binary in System Settings > Privacy & Security > Accessibility.")
            } else if !didPrompt {
                log("accessibility permission is required. Re-run without --no-prompt if you want the system prompt.")
                didPrompt = true
            }

            Thread.sleep(forTimeInterval: 3.0)
        }
    }

    private func scanOnce() {
        let runningApps = NSWorkspace.shared.runningApplications.filter { app in
            app.localizedName == options.targetAppName && !app.isTerminated
        }

        guard !runningApps.isEmpty else {
            return
        }

        for app in runningApps {
            let appElement = AXUIElementCreateApplication(app.processIdentifier)
            let roots = rootElements(for: appElement)
            var candidates: [CandidateButton] = []
            for root in roots {
                candidates.append(contentsOf: findCandidateButtons(in: root))
            }

            let rankedCandidates = dedupCandidates(candidates).sorted { lhs, rhs in
                if lhs.priority != rhs.priority {
                    return lhs.priority > rhs.priority
                }
                return lhs.title < rhs.title
            }

            for candidate in rankedCandidates {
                guard shouldClick(candidate.button, signature: candidate.signature) else {
                    continue
                }

                let action = options.dryRun ? "would click" : "clicked"
                log("\(action): pid=\(app.processIdentifier) title=\(candidate.title) priority=\(candidate.priorityLabel) context=\(candidate.context)")

                if !options.dryRun {
                    let result = AXUIElementPerformAction(candidate.button, kAXPressAction as CFString)
                    if result != .success {
                        log("press failed for \(candidate.title): \(result.rawValue)")
                        continue
                    }
                }

                lastClickAtBySignature[candidate.signature] = Date()
                break
            }
        }
    }

    private func shouldClick(_ button: AXUIElement, signature: String) -> Bool {
        guard isEnabled(button) else {
            return false
        }

        if let lastClickAt = lastClickAtBySignature[signature],
           Date().timeIntervalSince(lastClickAt) < dedupeInterval {
            return false
        }

        return true
    }

    private func rootElements(for appElement: AXUIElement) -> [AXUIElement] {
        var roots: [AXUIElement] = [appElement]

        if let focusedWindow = attributeElement(appElement, kAXFocusedWindowAttribute) {
            roots.append(focusedWindow)
        }
        if let mainWindow = attributeElement(appElement, kAXMainWindowAttribute) {
            roots.append(mainWindow)
        }
        roots.append(contentsOf: attributeElements(appElement, kAXWindowsAttribute))
        roots.append(contentsOf: attributeElements(appElement, axSheetsAttribute))

        return dedupElements(roots)
    }

    private func findCandidateButtons(in root: AXUIElement) -> [CandidateButton] {
        var visited = Set<Int>()
        return findCandidateButtons(in: root, depth: 0, visited: &visited)
    }

    private func findCandidateButtons(
        in element: AXUIElement,
        depth: Int,
        visited: inout Set<Int>
    ) -> [CandidateButton] {
        if depth > 8 {
            return []
        }

        let hash = Int(CFHash(element))
        if visited.contains(hash) {
            return []
        }
        visited.insert(hash)

        var matches: [CandidateButton] = []

        if role(of: element) == kAXButtonRole as String,
           let title = title(of: element),
           let preference = buttonPreference(for: title) {
            let container = nearestDialogContainer(from: element) ?? element
            let context = summarize(container: container)
            let signature = "\(hash)|\(title)|\(context)"
            matches.append(
                CandidateButton(
                    button: element,
                    title: title,
                    priority: preference.priority,
                    priorityLabel: preference.label,
                    context: context,
                    signature: signature
                )
            )
        }

        for child in childElements(of: element) {
            matches.append(contentsOf: findCandidateButtons(in: child, depth: depth + 1, visited: &visited))
        }

        return matches
    }

    private func nearestDialogContainer(from element: AXUIElement) -> AXUIElement? {
        var current: AXUIElement? = element

        while let node = current {
            if let role = role(of: node),
               role == kAXSheetRole as String || role == kAXWindowRole as String {
                return node
            }
            if let subrole = subrole(of: node), subrole == kAXDialogSubrole as String {
                return node
            }
            current = attributeElement(node, kAXParentAttribute)
        }

        return nil
    }

    private func summarize(container: AXUIElement) -> String {
        var pieces: [String] = []

        if let title = title(of: container), !title.isEmpty {
            pieces.append(title)
        }
        if let description = attributeString(container, kAXDescriptionAttribute), !description.isEmpty {
            pieces.append(description)
        }

        collectInterestingText(in: container, depth: 0, into: &pieces)

        let cleaned = pieces
            .map { $0.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        if cleaned.isEmpty {
            return "(no accessible context)"
        }

        return Array(cleaned.prefix(6)).joined(separator: " | ")
    }

    private func collectInterestingText(in element: AXUIElement, depth: Int, into pieces: inout [String]) {
        if depth > 3 || pieces.count >= 6 {
            return
        }

        if let role = role(of: element),
           role == kAXStaticTextRole as String || role == kAXTextFieldRole as String,
           let value = stringValue(of: element),
           !value.isEmpty {
            pieces.append(value)
        }

        for child in childElements(of: element).prefix(20) {
            collectInterestingText(in: child, depth: depth + 1, into: &pieces)
            if pieces.count >= 6 {
                return
            }
        }
    }

    private func childElements(of element: AXUIElement) -> [AXUIElement] {
        let attributes: [String] = [
            kAXChildrenAttribute,
            axSheetsAttribute,
            kAXWindowsAttribute
        ]

        var collected: [AXUIElement] = []
        for attributeName in attributes {
            collected.append(contentsOf: attributeElements(element, attributeName))
            if let node = attributeElement(element, attributeName) {
                collected.append(node)
            }
        }

        return dedupElements(collected)
    }

    private func dedupCandidates(_ candidates: [CandidateButton]) -> [CandidateButton] {
        var dedupedBySignature: [String: CandidateButton] = [:]

        for candidate in candidates {
            if let existing = dedupedBySignature[candidate.signature] {
                if candidate.priority > existing.priority {
                    dedupedBySignature[candidate.signature] = candidate
                }
            } else {
                dedupedBySignature[candidate.signature] = candidate
            }
        }

        return Array(dedupedBySignature.values)
    }

    private func dedupElements(_ elements: [AXUIElement]) -> [AXUIElement] {
        var seen = Set<Int>()
        var deduped: [AXUIElement] = []

        for element in elements {
            let hash = Int(CFHash(element))
            if seen.insert(hash).inserted {
                deduped.append(element)
            }
        }

        return deduped
    }

    private func isEnabled(_ element: AXUIElement) -> Bool {
        attributeBool(element, kAXEnabledAttribute) ?? true
    }

    private func role(of element: AXUIElement) -> String? {
        attributeString(element, kAXRoleAttribute)
    }

    private func subrole(of element: AXUIElement) -> String? {
        attributeString(element, kAXSubroleAttribute)
    }

    private func title(of element: AXUIElement) -> String? {
        if let title = attributeString(element, kAXTitleAttribute) {
            return title
        }
        return attributeString(element, kAXValueAttribute)
    }

    private func stringValue(of element: AXUIElement) -> String? {
        if let value = attributeString(element, kAXValueAttribute) {
            return value
        }
        return attributeString(element, kAXTitleAttribute)
    }

    private func buttonPreference(for title: String) -> ButtonPreference? {
        let normalized = normalize(title)

        if normalized.contains("always allow for project") ||
            (normalized.contains("always allow") && normalized.contains("project")) ||
            (normalized.contains("常に許可") && normalized.contains("プロジェクト")) {
            return ButtonPreference(priority: 400, label: "always-allow-project")
        }

        if normalized == "always allow" || normalized.contains("always allow") || normalized.contains("常に許可") {
            return ButtonPreference(priority: 300, label: "always-allow")
        }

        if normalized == "allow once" || normalized.contains("allow once") || normalized.contains("一度だけ許可") {
            return ButtonPreference(priority: 200, label: "allow-once")
        }

        if normalized == "allow" || normalized == "許可" {
            return ButtonPreference(priority: 100, label: "allow")
        }

        return nil
    }

    private func normalize(_ text: String) -> String {
        text
            .folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: .current)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    private func attributeValue(_ element: AXUIElement, _ attribute: String) -> CFTypeRef? {
        var value: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
        guard result == .success, let value else {
            return nil
        }
        return value
    }

    private func attributeString(_ element: AXUIElement, _ attribute: String) -> String? {
        guard let value = attributeValue(element, attribute) else {
            return nil
        }
        return value as? String
    }

    private func attributeBool(_ element: AXUIElement, _ attribute: String) -> Bool? {
        guard let value = attributeValue(element, attribute) else {
            return nil
        }
        return value as? Bool
    }

    private func attributeElement(_ element: AXUIElement, _ attribute: String) -> AXUIElement? {
        guard let value = attributeValue(element, attribute), CFGetTypeID(value) == AXUIElementGetTypeID() else {
            return nil
        }
        return unsafeBitCast(value, to: AXUIElement.self)
    }

    private func attributeElements(_ element: AXUIElement, _ attribute: String) -> [AXUIElement] {
        guard let value = attributeValue(element, attribute), CFGetTypeID(value) == CFArrayGetTypeID() else {
            return []
        }

        let array = unsafeBitCast(value, to: NSArray.self)
        return array.compactMap { item in
            let reference = item as CFTypeRef
            guard CFGetTypeID(reference) == AXUIElementGetTypeID() else {
                return nil
            }
            return unsafeBitCast(reference, to: AXUIElement.self)
        }
    }

    private func log(_ message: String) {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        print("[\(formatter.string(from: Date()))] \(message)")
        fflush(stdout)
    }
}

struct CandidateButton {
    let button: AXUIElement
    let title: String
    let priority: Int
    let priorityLabel: String
    let context: String
    let signature: String
}

struct ButtonPreference {
    let priority: Int
    let label: String
}

func parseOptions() -> Options {
    var options = Options()
    var iterator = CommandLine.arguments.dropFirst().makeIterator()

    while let argument = iterator.next() {
        switch argument {
        case "--dry-run":
            options.dryRun = true
        case "--once":
            options.singlePass = true
        case "--no-prompt":
            options.promptForAccessibility = false
        case "--interval":
            if let rawValue = iterator.next(), let value = TimeInterval(rawValue), value > 0 {
                options.interval = value
            }
        case "--help", "-h":
            print("""
            Usage: claude_allow_watcher.swift [options]

              --dry-run     log matches without clicking
              --once        scan one time and exit
              --no-prompt   do not open the accessibility permission prompt
              --interval N  polling interval in seconds (default: 0.7)
            """)
            exit(0)
        default:
            fputs("unknown argument: \(argument)\n", stderr)
            exit(2)
        }
    }

    return options
}

let watcher = ClaudeAllowWatcher(options: parseOptions())
watcher.run()
