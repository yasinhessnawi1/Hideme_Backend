package models

// DetectionMethod represents a method used to identify sensitive information in documents.
// The system supports multiple detection methods, each with its own visual identifier.
type DetectionMethod struct {
	ID             int64  `json:"id" db:"method_id"`
	MethodName     string `json:"method_name" db:"method_name"`
	HighlightColor string `json:"highlight_color" db:"highlight_color"`
}

// TableName returns the database table name for the DetectionMethod model.
func (dm *DetectionMethod) TableName() string {
	return "detection_methods"
}

// Predefined detection methods for use within the application.
const (
	DetectionMethodManual        = "Manual"
	DetectionMethodSearch        = "Search"
	DetectionMethodAiSearch      = "AiSearch"
	DetectionMethodCaseSensitive = "CaseSensitive"
	DetectionMethodMLModel1      = "Presidio" // presidio
	DetectionMethodMLModel2      = "Gliner"   // Gliner
	DetectionMethodAIModel       = "Gemini"   // Gemini
	DetectionMethodHideMeModel   = "HideMeModel"
)

// DefaultDetectionMethods returns the default detection methods used by the application.
// These will be seeded in the database during initial setup.
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
