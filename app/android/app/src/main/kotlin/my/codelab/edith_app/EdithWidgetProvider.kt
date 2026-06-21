package my.codelab.edith_app

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import android.widget.RemoteViews
import es.antonborri.home_widget.HomeWidgetLaunchIntent
import es.antonborri.home_widget.HomeWidgetProvider

/**
 * Simple home-screen widget: shows a status line and launches EDITH into a
 * voice session when tapped (deep link edith://voice handled by the Flutter app
 * via home_widget's widgetClicked / initiallyLaunchedFromHomeWidget).
 *
 * Extends HomeWidgetProvider (the package's AppWidgetProvider subclass) so
 * onUpdate is handed the saved widget data directly. RemoteViews only — no
 * Glance/Compose — to keep the Android build minimal.
 */
class EdithWidgetProvider : HomeWidgetProvider() {
    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray,
        widgetData: SharedPreferences,
    ) {
        for (appWidgetId in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.edith_widget).apply {
                val status = widgetData.getString("edith_status", null) ?: "Tap to talk"
                setTextViewText(R.id.widget_status, status)

                // Tapping the widget launches the app on the edith://voice URI.
                val pendingIntent = HomeWidgetLaunchIntent.getActivity(
                    context,
                    MainActivity::class.java,
                    Uri.parse("edith://voice"),
                )
                setOnClickPendingIntent(R.id.widget_root, pendingIntent)
            }
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}
