package dev.koschei.langmobile

import android.app.Activity
import android.os.Bundle
import android.content.Intent
import android.graphics.Typeface
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var editor: EditText
    private lateinit var status: TextView
    private val openDocument = 100
    private val saveDocument = 101

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        val title = TextView(this).apply {
            text = "Koschei Lang Mobile · v0.2"
            textSize = 20f
        }
        editor = EditText(this).apply {
            setText("fn main() {\n    println(\"Koschei\")\n}\n")
            typeface = Typeface.MONOSPACE
            textSize = 15f
            gravity = android.view.Gravity.TOP
            setHorizontallyScrolling(true)
        }
        status = TextView(this).apply {
            text = "Hazır · Dosya kaydetme doğrulaması etkin"
            textSize = 16f
            setTextColor(android.graphics.Color.BLACK)
            setPadding(0, 12, 0, 12)
        }
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val open = Button(this).apply {
            text = "Aç"
            setOnClickListener {
                startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                }, openDocument)
            }
        }
        val save = Button(this).apply {
            text = "Kaydet"
            setOnClickListener {
                startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TITLE, "main.ks")
                }, saveDocument)
            }
        }
        actions.addView(open)
        actions.addView(save)
        layout.addView(title)
        layout.addView(actions)
        layout.addView(status)
        layout.addView(editor, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(layout)
    }

    @Deprecated("Deprecated in Android framework; sufficient for v0.1 document picker")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        try {
            when (requestCode) {
                openDocument -> {
                    val text = contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                        ?: throw IllegalStateException("Dosya okunamadı")
                    if (text.isEmpty()) {
                        status.text = "UYARI: Dosya boş (0 bayt); mevcut kod korundu"
                    } else {
                        editor.setText(text)
                        status.text = "Dosya açıldı: ${text.toByteArray(Charsets.UTF_8).size} bayt"
                    }
                }
                saveDocument -> {
                    val code = editor.text.toString()
                    if (code.isBlank()) {
                        status.text = "UYARI: Editör boş; dosya kaydedilmedi"
                        return
                    }
                    contentResolver.openOutputStream(uri, "w")?.use { output ->
                        output.write(code.toByteArray(Charsets.UTF_8))
                        output.flush()
                    } ?: throw IllegalStateException("Dosya yazılamadı")
                    val saved = contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                        ?: throw IllegalStateException("Dosya tekrar okunamadı")
                    if (saved != code) throw IllegalStateException("Kaydedilen içerik doğrulanamadı")
                    status.text = "Kaydedildi ve doğrulandı: ${code.toByteArray(Charsets.UTF_8).size} bayt"
                }
            }
        } catch (e: Exception) {
            status.text = "Dosya işlemi başarısız: ${e.javaClass.simpleName}"
        }
    }
}
