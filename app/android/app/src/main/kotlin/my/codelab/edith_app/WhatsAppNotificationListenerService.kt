package my.codelab.edith_app

import android.app.Notification
import android.app.RemoteInput
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Captures incoming WhatsApp notifications (package com.whatsapp) via the
 * official NotificationListenerService API and exposes a direct-reply path
 * through the notification's RemoteInput action.
 *
 * This is the locked "personal assist" track: official OS APIs, on-device, no
 * server session, and explicitly NOT WhatsApp Web scraping. iOS cannot do this.
 *
 * The Dart side talks to this through [WhatsAppChannel] (method/event channels
 * wired in MainActivity). Reply actions are cached per notification key so a
 * later reply() RPC can fire the correct RemoteInput.
 */
class WhatsAppNotificationListenerService : NotificationListenerService() {

    companion object {
        private const val WHATSAPP_PACKAGE = "com.whatsapp"

        /** Cached reply actions keyed by StatusBarNotification.key. */
        private val replyActions = HashMap<String, Notification.Action>()
        private val replyContexts = HashMap<String, Bundle>()

        /**
         * Fire a cached RemoteInput reply for [key]. Returns false if no
         * reply-capable notification is known for that key.
         */
        fun sendReply(context: Context, key: String, text: String): Boolean {
            val action = replyActions[key] ?: return false
            val remoteInputs = action.remoteInputs ?: return false

            val intent = Intent()
            val results = Bundle()
            for (remoteInput in remoteInputs) {
                results.putCharSequence(remoteInput.resultKey, text)
            }
            RemoteInput.addResultsToIntent(remoteInputs, intent, results)
            return try {
                action.actionIntent.send(context, 0, intent)
                true
            } catch (e: Exception) {
                false
            }
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName != WHATSAPP_PACKAGE) {
            return
        }
        val notification = sbn.notification ?: return
        val extras = notification.extras ?: return

        val sender = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
        // WhatsApp posts group-summary and call notifications too; skip empties.
        if (text.isBlank()) {
            return
        }

        val replyAction = findReplyAction(notification)
        if (replyAction != null) {
            replyActions[sbn.key] = replyAction
            replyContexts[sbn.key] = extras
        }

        WhatsAppChannel.emitIncoming(
            mapOf(
                "sender" to sender,
                "text" to text,
                "key" to sbn.key,
                "canReply" to (replyAction != null),
                "timestamp" to sbn.postTime,
            )
        )
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        replyActions.remove(sbn.key)
        replyContexts.remove(sbn.key)
    }

    /** Find the first action that carries a RemoteInput (the direct-reply one). */
    private fun findReplyAction(notification: Notification): Notification.Action? {
        val actions = notification.actions ?: return null
        return actions.firstOrNull { action ->
            action.remoteInputs?.isNotEmpty() == true
        }
    }
}
