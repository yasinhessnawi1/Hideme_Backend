package migrations

import (
	"context"
	"database/sql"
)

// createUsersTable creates the users table
func createUsersTable() Migration {
	return Migration{
		Name:        "create_users_table",
		Description: "Creates the users table",
		TableName:   "users",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
				CREATE TABLE IF NOT EXISTS users (
					user_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
					username VARCHAR(50) NOT NULL,
					email VARCHAR(255) NOT NULL,
					password_hash VARCHAR(255) NOT NULL,
					salt VARCHAR(255) NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					CONSTRAINT idx_username UNIQUE (username),
					CONSTRAINT idx_email UNIQUE (email)
				)
			`
			_, err := tx.ExecContext(ctx, query)
			return err
		},
	}
}

// createUserSettingsTable creates the user_settings table
func createUserSettingsTable() Migration {
	return Migration{
		Name:        "create_user_settings_table",
		Description: "Creates the user_settings table",
		TableName:   "user_settings",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS user_settings (
                    setting_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    user_id BIGINT NOT NULL,
                    remove_images BOOLEAN DEFAULT FALSE,
                    theme VARCHAR(10) DEFAULT 'system' CHECK (theme IN ('system', 'light', 'dark')),
					use_banlist_for_detection BOOLEAN DEFAULT TRUE,
					detection_threshold DECIMAL(5, 2) DEFAULT 0.50,
                    auto_processing BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    CONSTRAINT idx_user_id UNIQUE (user_id)
                )
            `
			_, err := tx.ExecContext(ctx, query)
			return err
		},
	}
}

// createDocumentsTable creates the documents table
func createDocumentsTable() Migration {
	return Migration{
		Name:        "create_documents_table",
		Description: "Creates the documents table",
		TableName:   "documents",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
				CREATE TABLE IF NOT EXISTS documents (
					document_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
					user_id BIGINT NOT NULL,
					hashed_document_name VARCHAR(255) NOT NULL,
					upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
				)
			`
			// Create index separately
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			indexQuery := `CREATE INDEX IF NOT EXISTS idx_user_id ON documents(user_id)`
			_, err = tx.ExecContext(ctx, indexQuery)
			return err
		},
	}
}

// createSearchPatternsTable creates the search_patterns table
func createSearchPatternsTable() Migration {
	return Migration{
		Name:        "create_search_patterns_table",
		Description: "Creates the search_patterns table",
		TableName:   "search_patterns",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS search_patterns (
                    pattern_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    setting_id BIGINT NOT NULL,
                    pattern_type VARCHAR(15) NOT NULL DEFAULT 'Normal' CHECK (pattern_type IN ('ai_search', 'normal', 'case_sensitive')),
                    pattern_text TEXT NOT NULL DEFAULT '',
                    CONSTRAINT fk_setting FOREIGN KEY (setting_id) REFERENCES user_settings(setting_id) ON DELETE CASCADE
                )
            `
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			indexQuery := `CREATE INDEX IF NOT EXISTS idx_setting_id ON search_patterns(setting_id)`
			_, err = tx.ExecContext(ctx, indexQuery)
			return err
		},
	}
}

// createDetectionMethodsTable creates the detection_methods table
func createDetectionMethodsTable() Migration {
	return Migration{
		Name:        "create_detection_methods_table",
		Description: "Creates the detection_methods table",
		TableName:   "detection_methods",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS detection_methods (
                    method_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    method_name VARCHAR(50) NOT NULL DEFAULT '',
                    highlight_color VARCHAR(20) NOT NULL DEFAULT '#FFFFFF',
                    CONSTRAINT idx_method_name UNIQUE (method_name)
                )
            `
			_, err := tx.ExecContext(ctx, query)
			return err
		},
	}
}

// createDetectedEntitiesTable creates the detected_entities table
func createDetectedEntitiesTable() Migration {
	return Migration{
		Name:        "create_detected_entities_table",
		Description: "Creates the detected_entities table",
		TableName:   "detected_entities",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS detected_entities (
                    entity_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    document_id BIGINT NOT NULL,
                    method_id BIGINT NOT NULL,
                    entity_name VARCHAR(255) NOT NULL DEFAULT '',
                    redaction_schema JSONB NOT NULL DEFAULT '{}',
                    detected_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_document FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
                    CONSTRAINT fk_method FOREIGN KEY (method_id) REFERENCES detection_methods(method_id)
                )
            `
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			// Create indexes separately
			indexes := []string{
				`CREATE INDEX IF NOT EXISTS idx_document_id ON detected_entities(document_id)`,
				`CREATE INDEX IF NOT EXISTS idx_method_id ON detected_entities(method_id)`,
				`CREATE INDEX IF NOT EXISTS idx_entity_name ON detected_entities(entity_name)`,
			}

			for _, idx := range indexes {
				_, err = tx.ExecContext(ctx, idx)
				if err != nil {
					return err
				}
			}

			return nil
		},
	}
}

// createModelEntitiesTable creates the model_entities table
func createModelEntitiesTable() Migration {
	return Migration{
		Name:        "create_model_entities_table",
		Description: "Creates the model_entities table",
		TableName:   "model_entities",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS model_entities (
                    model_entity_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    setting_id BIGINT NOT NULL,
                    method_id BIGINT NOT NULL,
                    entity_text VARCHAR(255) NOT NULL DEFAULT '',
                    CONSTRAINT fk_setting FOREIGN KEY (setting_id) REFERENCES user_settings(setting_id) ON DELETE CASCADE,
                    CONSTRAINT fk_method FOREIGN KEY (method_id) REFERENCES detection_methods(method_id)
                )
            `
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			// Create indexes separately
			indexes := []string{
				`CREATE INDEX IF NOT EXISTS idx_setting_id ON model_entities(setting_id)`,
				`CREATE INDEX IF NOT EXISTS idx_method_id ON model_entities(method_id)`,
			}

			for _, idx := range indexes {
				_, err = tx.ExecContext(ctx, idx)
				if err != nil {
					return err
				}
			}

			return nil
		},
	}
}

// createBanListsTable (added because it's referenced but was missing)
func createBanListTable() Migration {
	return Migration{
		Name:        "create_ban_lists_table",
		Description: "Creates the ban_lists table",
		TableName:   "ban_lists",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS ban_lists (
                    ban_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    setting_id BIGINT NOT NULL,
                    CONSTRAINT fk_setting FOREIGN KEY (setting_id) REFERENCES user_settings(setting_id) ON DELETE CASCADE,
                    CONSTRAINT idx_setting_id_1 UNIQUE (setting_id)
                )
            `
			_, err := tx.ExecContext(ctx, query)
			return err
		},
	}
}

// createBanListWordsTable creates the ban_list_words table
func createBanListWordsTable() Migration {
	return Migration{
		Name:        "create_ban_list_words_table",
		Description: "Creates the ban_list_words table",
		TableName:   "ban_list_words",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
                CREATE TABLE IF NOT EXISTS ban_list_words (
                    ban_word_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    ban_id BIGINT NOT NULL,
                    word VARCHAR(255) NOT NULL DEFAULT '',
                    CONSTRAINT fk_ban_list FOREIGN KEY (ban_id) REFERENCES ban_lists(ban_id) ON DELETE CASCADE,
                    CONSTRAINT idx_ban_word UNIQUE (ban_id, word)
                )
            `
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			// Create indexes separately
			indexes := []string{
				`CREATE INDEX IF NOT EXISTS idx_ban_id ON ban_list_words(ban_id)`,
				`CREATE INDEX IF NOT EXISTS idx_word ON ban_list_words(word)`,
			}

			for _, idx := range indexes {
				_, err = tx.ExecContext(ctx, idx)
				if err != nil {
					return err
				}
			}

			return nil
		},
	}
}

// createSessionsTable creates the sessions table
func createSessionsTable() Migration {
	return Migration{
		Name:        "create_sessions_table",
		Description: "Creates the sessions table",
		TableName:   "sessions",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
				CREATE TABLE IF NOT EXISTS sessions (
					session_id VARCHAR(255) PRIMARY KEY,
					user_id BIGINT NOT NULL,
					jwt_id VARCHAR(255) NOT NULL,
					expires_at TIMESTAMP NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
				)
			`
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			// Create indexes separately
			indexes := []string{
				`CREATE INDEX IF NOT EXISTS idx_user_id ON sessions(user_id)`,
				`CREATE INDEX IF NOT EXISTS idx_jwt_id ON sessions(jwt_id)`,
				`CREATE INDEX IF NOT EXISTS idx_expires_at ON sessions(expires_at)`,
			}

			for _, idx := range indexes {
				_, err = tx.ExecContext(ctx, idx)
				if err != nil {
					return err
				}
			}

			return nil
		},
	}
}

// createAPIKeysTable creates the api_keys table
func createAPIKeysTable() Migration {
	return Migration{
		Name:        "create_api_keys_table",
		Description: "Creates the api_keys table",
		TableName:   "api_keys",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
				CREATE TABLE IF NOT EXISTS api_keys (
					key_id VARCHAR(255) PRIMARY KEY,
					user_id BIGINT NOT NULL,
					api_key_hash VARCHAR(255) NOT NULL,
					name VARCHAR(100) NOT NULL,
					expires_at TIMESTAMP NOT NULL,
					created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
					CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
				)
			`
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			// Create indexes separately
			indexes := []string{
				`CREATE INDEX IF NOT EXISTS idx_user_id ON api_keys(user_id)`,
				`CREATE INDEX IF NOT EXISTS idx_expires_at ON api_keys(expires_at)`,
			}

			for _, idx := range indexes {
				_, err = tx.ExecContext(ctx, idx)
				if err != nil {
					return err
				}
			}

			return nil
		},
	}
}
