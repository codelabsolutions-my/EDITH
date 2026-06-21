package my.codelab.edith_app

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

/**
 * Wires the WhatsApp assist platform channels to the
 * [WhatsAppNotificationListenerService].
 *
 *   * method channel `edith/whatsapp` — hasPermission / openPermissionSettings / reply
 *   * event channel  `edith/whatsapp/incoming` — incoming message stream
 *
 * Incoming events that arrive before Dart attaches a listener are buffered so
 * none are lost during startup.
 */
object WhatsAppChannel : EventChannel.StreamHandler {
    private const val METHOD_CHANNEL = "edith/whatsapp"
    private const val EVENT_CHANNEL = "edith/whatsapp/incoming"

    private var eventSink: EventChannel.EventSink? = null
    private val pending = ArrayList<Map<String, Any?>>()
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var appContext: Context

    fun register(engine: FlutterEngine, context: Context) {
        appContext = context.applicationContext
        val messenger = engine.dartExecutor.binaryMessenger

        MethodChannel(messenger, METHOD_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "hasPermission" -> result.success(isListenerEnabled())
                "openPermissionSettings" -> {
                    openSettings()
                    result.success(null)
                }
                "reply" -> {
                    val key = call.argument<String>("key")
                    val text = call.argument<String>("text")
                    if (key == null || text == null) {
                        result.error("bad_args", "key and text are required", null)
                    } else {
                        val ok = WhatsAppNotificationListenerService.sendReply(
                            appContext, key, text,
                        )
                        result.success(ok)
                    }
                }
                else -> result.notImplemented()
            }
        }

        EventChannel(messenger, EVENT_CHANNEL).setStreamHandler(this)
    }

    /** Called by the listener service when a WhatsApp message is captured. */
    fun emitIncoming(message: Map<String, Any?>) {
        mainHandler.post {
            val sink = eventSink
            if (sink != null) {
                sink.success(message)
            } else {
                pending.add(message)
            }
        }
    }

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
        eventSink = events
        if (events != null) {
            for (message in pending) {
                events.success(message)
            }
            pending.clear()
        }
    }

    override fun onCancel(arguments: Any?) {
        eventSink = null
    }

    /** Whether our notification listener has been granted access. */
    private fun isListenerEnabled(): Boolean {
        val enabled = NotificationManagerCompat.getEnabledListenerPackages(appContext)
        if (appContext.packageName in enabled) {
            return true
        }
        // Fallback to the raw flat-string check (covers older devices).
        val flat = Settings.Secure.getString(
            appContext.contentResolver, "enabled_notification_listeners",
        ) ?: return false
        val component = ComponentName(
            appContext, WhatsAppNotificationListenerService::class.java,
        )
        return flat.split(":").any {
            ComponentName.unflattenFromString(it) == component
        }
    }

    private fun openSettings() {
        val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        appContext.startActivity(intent)
    }
}
