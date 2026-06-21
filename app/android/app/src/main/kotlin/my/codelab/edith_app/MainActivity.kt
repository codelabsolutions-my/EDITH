package my.codelab.edith_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // Wire the WhatsApp personal-assist platform channels.
        WhatsAppChannel.register(flutterEngine, this)
    }
}
