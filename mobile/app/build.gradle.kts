import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Read the licensing secret from a gitignored file so it's NEVER committed.
// Copy secret.properties.example -> secret.properties and paste your secret.key
// hex value (the SAME secret your desktop License Console signs with).
val secretProps = Properties().apply {
    val f = rootProject.file("secret.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val umdSecret: String = (secretProps.getProperty("UMD_SECRET") ?: "").trim()

android {
    namespace = "ke.co.baziqhue.umd"
    compileSdk = 34

    defaultConfig {
        applicationId = "ke.co.baziqhue.umd"
        minSdk = 26          // 26 lets us ship a vector adaptive icon (no PNGs)
        targetSdk = 34
        versionCode = 5
        versionName = "1.4"

        // Baked into BuildConfig at build time (not in the repo).
        buildConfigField("String", "UMD_SECRET", "\"$umdSecret\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
    packaging {
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
        // youtubedl-android ships native libs per ABI
        jniLibs { useLegacyPackaging = true }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
    implementation("androidx.activity:activity-compose:1.9.1")

    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    // The download engine: bundles Python + yt-dlp + ffmpeg for Android.
    // (If a version is not found, let Android Studio suggest the latest.)
    implementation("io.github.junkfood02.youtubedl-android:library:0.17.2")
    implementation("io.github.junkfood02.youtubedl-android:ffmpeg:0.17.2")
    implementation("io.github.junkfood02.youtubedl-android:aria2c:0.17.2")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
