// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "CTMCompanion",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "CTMCompanion",
            targets: ["CTMCompanion"]
        )
    ],
    targets: [
        .executableTarget(
            name: "CTMCompanion",
            dependencies: [],
            resources: [
                .copy("Resources/Scripts")
            ]
        )
    ]
)
