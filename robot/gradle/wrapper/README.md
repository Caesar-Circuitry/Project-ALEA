# robot/gradle/wrapper

The Gradle wrapper. Use `./gradlew` (Unix) or `.\gradlew.bat` (Windows) from `robot/`, so
everyone builds with the same Gradle version without installing it.

- `gradle-wrapper.jar`: the bootstrap that downloads Gradle. Do not edit it.
- `gradle-wrapper.properties`: the Gradle version (9.1.0), the download URL and its SHA-256
  (`distributionSha256Sum`). `validateDistributionUrl=true` checks the URL.

Dependabot proposes Gradle updates for `/robot` (see `.github/dependabot.yml`).

**Roadmap phase:** Phase 0 (contract), filled in PR 5
