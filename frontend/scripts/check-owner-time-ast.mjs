#!/usr/bin/env node
/**
 * Production owner-time invariant (bu-6jv4m.14).
 *
 * Display timestamps must use components/ui/time.tsx. This AST gate catches
 * locale-sensitive Date formatting and hard-coded UTC display formatters in
 * production source. The small exception list is deliberately path-based:
 * those files format backend date keys or derive calendar/query boundaries,
 * not event timestamps shown to the owner.
 */
import fs from "node:fs"
import path from "node:path"
import ts from "typescript"

const ROOT = path.resolve(new URL("..", import.meta.url).pathname)
const SRC = path.join(ROOT, "src")
const DISPLAY_EXCEPTIONS = new Set([
  "components/costs/CostStripeChart.tsx",
  "components/chronicles/RecentDaysIndex.tsx",
  "components/health/MealTracker.tsx",
  "components/ingestion/filters/PrioritySendersBlock.tsx",
  "components/butler-detail/ButlerRelationshipContactsTab.tsx",
  "components/dashboard/session-stripe-utils.ts",
])
const CALENDAR_EXCEPTIONS = new Set([
  "lib/day-window.ts",
  "lib/hourly-buckets.ts",
  "lib/memory-derived.ts",
  "lib/medication-schedule.ts",
  "components/chronicles/RecentDaysIndex.tsx",
  "components/chronicles/WorkScheduleSettings.tsx",
  "pages/CalendarWorkspacePage.tsx",
  "pages/ApprovalsPage.tsx",
  "components/costs/CostStripeChart.tsx",
  "components/dashboard/session-stripe-utils.ts",
])

function filesUnder(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return filesUnder(full)
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) return []
    return [full]
  })
}

function rel(file) {
  return path.relative(SRC, file).split(path.sep).join("/")
}

const violations = []
for (const file of filesUnder(SRC)) {
  const relative = rel(file)
  const source = fs.readFileSync(file, "utf8")
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true)
  function visit(node) {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const name = node.expression.name.text
      const directDate = ts.isNewExpression(node.expression.expression) &&
        ts.isIdentifier(node.expression.expression.expression) &&
        node.expression.expression.expression.text === "Date"
      if ((name === "toLocaleDateString" || name === "toLocaleTimeString" ||
        (name === "toLocaleString" && directDate)) && !DISPLAY_EXCEPTIONS.has(relative)) {
        const pos = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1
        violations.push(`${relative}:${pos}: use <Time> or formatOwnerDateTime instead of ${name}()`)
      }
    }
    if ((ts.isCallExpression(node) || ts.isNewExpression(node)) &&
      ts.isPropertyAccessExpression(node.expression) &&
      ts.isIdentifier(node.expression.expression) &&
      node.expression.expression.text === "Intl" &&
      node.expression.name.text === "DateTimeFormat" &&
      !CALENDAR_EXCEPTIONS.has(relative)) {
      const pos = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1
      violations.push(`${relative}:${pos}: use owner-time formatting instead of Intl.DateTimeFormat`)
    }
    if (ts.isPropertyAssignment(node) && node.name.getText(tree) === "timeZone" &&
      node.initializer.getText(tree).replaceAll("'", '"') === '"UTC"' &&
      !CALENDAR_EXCEPTIONS.has(relative)) {
      const pos = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1
      violations.push(`${relative}:${pos}: hard-coded UTC display timezone is forbidden`)
    }
    ts.forEachChild(node, visit)
  }
  visit(tree)
}

if (violations.length) {
  console.error("Owner-time AST gate failed:")
  for (const violation of violations) console.error(`- ${violation}`)
  process.exitCode = 1
} else {
  console.log(`Owner-time AST gate passed (${filesUnder(SRC).length} production files scanned)`)
}
