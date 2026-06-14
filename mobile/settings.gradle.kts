pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // youtubedl-android is published on JitPack
        maven { url = uri("https://jitpack.io") }
    }
}

rootProject.name = "UniversalMediaDownloader"
include(":app")
