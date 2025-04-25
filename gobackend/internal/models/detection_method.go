// Package models provides data structures and operations for the HideMe application.
// This file contains models related to detection methods used to identify sensitive information.
package models

// DetectionMethod represents a method used to identify sensitive information in documents.
// The system supports multiple detection methods, each with its own visual identifier.
// Detection methods include manual markup, search-based techniques, and machine learning models.
type DetectionMethod struct {
	// ID is the unique identifier for this detection method
	ID int64 `json:"id" db:"method_id"`

	// MethodName is the human-readable name of this detection method
	MethodName string `json:"method_name" db:"method_name"`

	// HighlightColor is the CSS color value used to visually distinguish entities found by this method
	HighlightColor string `json:"highlight_color" db:"highlight_color"`
}

// TableName returns the database table name for the DetectionMethod model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (dm *DetectionMethod) TableName() string {
	return "detection_methods"
}

// Predefined detection methods for use within the application.
// These constants provide standardization across the codebase and ensure
// consistent entity detection categorization.
const (
	// DetectionMethodManual represents human-identified sensitive information
	DetectionMethodManual = "Manual"

	// DetectionMethodSearch represents information found via simple text search
	DetectionMethodSearch = "Search"

	// DetectionMethodAiSearch represents information found via AI-assisted search
	DetectionMethodAiSearch = "AiSearch"

	// DetectionMethodCaseSensitive represents information found via case-sensitive text search
	DetectionMethodCaseSensitive = "CaseSensitive"

	// DetectionMethodMLModel1 represents information identified by the Presidio ML model
	DetectionMethodMLModel1 = "Presidio" // presidio

	// DetectionMethodMLModel2 represents information identified by the Gliner ML model
	DetectionMethodMLModel2 = "Gliner" // Gliner

	// DetectionMethodAIModel represents information identified by the Gemini AI model
	DetectionMethodAIModel = "Gemini" // Gemini

	// DetectionMethodHideMeModel represents information identified by the custom HideMe model
	DetectionMethodHideMeModel = "HideMeModel"
)

// DefaultDetectionMethods returns the default detection methods used by the application.
// These will be seeded in the database during initial setup.
//
// Returns:
//   - A slice of DetectionMethod instances with predefined names and colors
//
// The color coding system allows users to quickly understand how entities were identified:
// - Green: ML-based detection (Presidio, HideMeModel)
// - Purple: Gliner ML model
// - Yellow: AI-based detection (Gemini)
// - Blue: Search-based detection (AiSearch, CaseSensitive, Search)
// - Orange-red: Manual detection
func DefaultDetectionMethods() []DetectionMethod {
	return []DetectionMethod{
		{
			MethodName:     DetectionMethodMLModel1,
			HighlightColor: "#33FF57", // Green
		},
		{
			MethodName:     DetectionMethodMLModel2,
			HighlightColor: "#F033FF", // Purple
		},
		{
			MethodName:     DetectionMethodAIModel,
			HighlightColor: "#FFFF33", // Yellow
		},
		{
			MethodName:     DetectionMethodHideMeModel,
			HighlightColor: "#33FF57", //green
		},
		{
			MethodName:     DetectionMethodAiSearch,
			HighlightColor: "#33A8FF", // Blue
		},
		{
			MethodName:     DetectionMethodCaseSensitive,
			HighlightColor: "#33A8FF", // Blue
		},
		{
			MethodName:     DetectionMethodSearch,
			HighlightColor: "#33A8FF", // Blue
		},
		{
			MethodName:     DetectionMethodManual,
			HighlightColor: "#FF5733", // Orange-red
		},
	}
}
