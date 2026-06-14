package ke.co.baziqhue.umd

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import android.provider.Settings
import android.util.Base64
import org.json.JSONObject
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Offline, machine-bound license verification — a faithful port of the desktop
 * licensing.py so that keys issued by the SAME desktop License Console activate
 * the mobile app too.
 *
 * Key format:   UMDL-<base64url(payload)>.<base64url(HMAC_SHA256(secret, payload)[:16])>
 * Device ID:    UMD-XXXX-XXXX-XXXX  (first 12 hex of SHA-256 of the device id)
 *
 * The signing secret (BuildConfig.UMD_SECRET) is the SAME hex value as the
 * desktop secret.key. Symmetric HMAC — like the desktop, the secret in a shipped
 * build is extractable; acceptable at this scale (harden later with Ed25519).
 */
data class LicensePayload(
    val customer: String,
    val machineId: String,
    val plan: String,
    val issued: String,
    val expiry: String,
)

object Licensing {

    private fun secretBytes(): ByteArray {
        val s = BuildConfig.UMD_SECRET.trim()
        val isHex = s.isNotEmpty() && s.length % 2 == 0 &&
            s.all { it in "0123456789abcdefABCDEF" }
        return if (isHex) {
            ByteArray(s.length / 2) {
                ((Character.digit(s[it * 2], 16) shl 4) +
                    Character.digit(s[it * 2 + 1], 16)).toByte()
            }
        } else {
            s.toByteArray(Charsets.UTF_8)
        }
    }

    private fun hmac(msg: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secretBytes(), "HmacSHA256"))
        return mac.doFinal(msg)
    }

    private fun b64urlEncode(b: ByteArray): String =
        Base64.encodeToString(b, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)

    private fun b64urlDecode(s: String): ByteArray {
        val pad = (4 - s.length % 4) % 4
        return Base64.decode(s + "=".repeat(pad), Base64.URL_SAFE or Base64.NO_WRAP)
    }

    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var r = 0
        for (i in a.indices) r = r or (a[i].code xor b[i].code)
        return r == 0
    }

    @SuppressLint("HardwareIds")
    fun deviceId(ctx: Context): String {
        val aid = Settings.Secure.getString(
            ctx.contentResolver, Settings.Secure.ANDROID_ID
        ) ?: "unknown"
        val raw = "$aid|${Build.MANUFACTURER}|${Build.MODEL}"
        val hex = MessageDigest.getInstance("SHA-256")
            .digest(raw.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
            .uppercase(Locale.US)
        val x = hex.substring(0, 12)
        return "UMD-${x.substring(0, 4)}-${x.substring(4, 8)}-${x.substring(8, 12)}"
    }

    fun verify(code: String): LicensePayload? {
        val c = code.trim()
        if (!c.startsWith("UMDL-")) return null
        val parts = c.removePrefix("UMDL-").split(".")
        if (parts.size != 2) return null
        val pb = parts[0]
        val sb = parts[1]
        val expected = b64urlEncode(hmac(pb.toByteArray(Charsets.UTF_8)).copyOf(16))
        if (!constantTimeEquals(sb, expected)) return null
        return try {
            val j = JSONObject(String(b64urlDecode(pb), Charsets.UTF_8))
            if (!j.has("e") || !j.has("mid")) return null
            LicensePayload(
                customer = j.optString("c"),
                machineId = j.getString("mid"),
                plan = j.optString("p"),
                issued = j.optString("i"),
                expiry = j.getString("e"),
            )
        } catch (e: Exception) {
            null
        }
    }

    private fun expiryDate(e: String): Date? {
        for (f in listOf("yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd")) {
            try {
                return SimpleDateFormat(f, Locale.US).parse(e)
            } catch (_: Exception) {
            }
        }
        return null
    }

    fun isExpired(p: LicensePayload): Boolean {
        val d = expiryDate(p.expiry) ?: return true
        return Date().after(d)
    }
}

/** Stores the activated key and answers "is this device licensed right now?". */
class LicenseManager(private val ctx: Context) {
    private val prefs = ctx.getSharedPreferences("umd_license", Context.MODE_PRIVATE)

    fun deviceId(): String = Licensing.deviceId(ctx)

    private fun storedCode(): String? = prefs.getString("code", null)

    fun activate(code: String): Pair<Boolean, String> {
        val p = Licensing.verify(code)
            ?: return false to "Invalid or corrupted key."
        if (p.machineId.isNotEmpty() && p.machineId != deviceId())
            return false to "This key was issued for a different device."
        if (Licensing.isExpired(p))
            return false to "This key expired on ${p.expiry}."
        prefs.edit().putString("code", code.trim()).apply()
        return true to "Activated! Valid until ${p.expiry}."
    }

    fun isLicensed(): Boolean {
        val p = Licensing.verify(storedCode() ?: return false) ?: return false
        if (p.machineId.isNotEmpty() && p.machineId != deviceId()) return false
        return !Licensing.isExpired(p)
    }

    fun status(): String {
        val p = Licensing.verify(storedCode() ?: return "Not activated.")
            ?: return "Stored key is invalid."
        return if (Licensing.isExpired(p)) "Expired on ${p.expiry}."
        else "Licensed to ${p.customer.ifEmpty { "you" }} · valid until ${p.expiry}."
    }

    fun deactivate() = prefs.edit().remove("code").apply()
}
