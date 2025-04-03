# Build stage
FROM golang:1.24-alpine AS builder

# Set working directory to match the nested structure
WORKDIR /build

# Copy the entire repository first to preserve structure
COPY . .

# Switch to the gobackend directory for building
WORKDIR /Hideme_Backend/gobackend
COPY go.mod go.sum ./
# Download Go modules
RUN go mod download
COPY . .
RUN ls -la && find . -type f -name "*.go" | sort

# Build the application with proper path
RUN CGO_ENABLED=0 GOOS=linux go build -o hideapp ./cmd/api/main.go

# Runtime stage
FROM alpine:latest

# Create app directory
WORKDIR /app

# Install certificates for HTTPS requests
RUN apk --no-cache add ca-certificates tzdata

# Copy binary from build stage
COPY --from=builder /build/hideapp .
COPY --from=builder /build/configs ./configs

# Create directory for logs
RUN mkdir -p /var/log/hideapp

# Set executable permissions
RUN chmod +x /app/hideapp

# Expose the application port
EXPOSE 8080

# Run the application
CMD ["/app/hideapp"]