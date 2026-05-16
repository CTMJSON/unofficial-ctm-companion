import SwiftUI

struct BrandColors {
    // CTM Official Color Palette
    static let skyBlue = Color(red: 0.00, green: 0.74, blue: 0.96)           // #01bdf6
    static let nebulaBlue = Color(red: 0.03, green: 0.59, blue: 0.79)        // #0796ca
    static let darkMatterBlue = Color(red: 0.05, green: 0.37, blue: 0.55)    // #0e5e8c
    static let spaceNavy = Color(red: 0.09, green: 0.16, blue: 0.31)         // #16294f
    static let supernovaLime = Color(red: 0.84, green: 0.85, blue: 0.00)     // #d6da01
    static let galaxyGrey = Color(red: 0.20, green: 0.20, blue: 0.20)        // #333333

    // Primary: Use Sky Blue as primary, Nebula Blue for interactions
    static let primary = skyBlue
    static let primaryDark = nebulaBlue
    static let secondary = darkMatterBlue
    static let accent = spaceNavy

    // Semantic colors
    static let success = skyBlue
    static let warning = supernovaLime
    static let error = Color(red: 0.95, green: 0.2, blue: 0.2)

    // Backgrounds & Borders
    static let backgroundLight = Color(red: 0.97, green: 0.99, blue: 1.0)    // Very light (near white)
    static let backgroundCard = Color.white
    static let borderColor = Color(red: 0.9, green: 0.94, blue: 0.98)        // Light blue-tinted
    static let dividerColor = Color(red: 0.93, green: 0.96, blue: 0.98)

    // Text colors
    static let textPrimary = spaceNavy
    static let textSecondary = galaxyGrey
    static let textTertiary = Color(red: 0.55, green: 0.55, blue: 0.55)
}
