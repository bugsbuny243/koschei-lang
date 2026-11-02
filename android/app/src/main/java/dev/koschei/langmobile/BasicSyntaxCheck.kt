package dev.koschei.langmobile

/**
 * Conservative offline delimiter checker. NOT a Koschei parser or compiler.
 * Avoids claims of full syntax correctness; double-quoted strings are skipped; full language parsing is not attempted.
 */
object BasicSyntaxCheck {
    data class Finding(val line: Int, val message: String)

    fun inspect(source: String): List<Finding> {
        val stack = mutableListOf<Pair<Char, Int>>()
        var line = 1
        var quoted = false
        var escaped = false
        for (ch in source) {
            if (ch == '\n') {
                line++
                if (quoted) {
                    // A multiline string may be legal in the full language;
                    // leave its validation to the real compiler.
                }
                if (escaped) escaped = false
                continue
            }
            if (quoted) {
                if (escaped) { escaped = false; continue }
                if (ch == '\\') { escaped = true; continue }
                if (ch == '"') quoted = false
                continue
            }
            if (ch == '"') { quoted = true; continue }
            when (ch) {
                '(', '{', '[' -> stack.add(ch to line)
                ')', '}', ']' -> {
                    val expected = when (ch) { ')' -> '('; '}' -> '{'; else -> '[' }
                    val last = stack.lastOrNull()
                    if (last == null || last.first != expected) {
                        return listOf(Finding(line, "Beklenmeyen kapanış: $ch"))
                    }
                    stack.removeAt(stack.lastIndex)
                }
            }
        }
        val remaining = stack.lastOrNull()
        if (remaining != null) return listOf(Finding(remaining.second, "Kapanmamış işaret: ${remaining.first}"))
        return emptyList()
    }
}
