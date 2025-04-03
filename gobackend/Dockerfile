# Build stage
FROM golang:1.24-alpine AS builder

# Set working directory to match the nested structure
WORKDIR /build

# Copy the entire repository first to preserve structure
COPY . .

# Switch to the gobackend directory for building
WORKDIR /build/gobackend

# Download Go modules
RUN go mod download

# Build the application with proper path
RUN CGO_ENABLED=0 GOOS=linux go build -o hideapp ./cmd/api/main.go

# Runtime stage
FROM alpine:latest

# Create app directory
WORKDIR /Hideme_Backend/gobackend

# Install certificates for HTTPS requests
RUN apk --no-cache add ca-certificates tzdata

# Copy binary from build stage
COPY --from=builder /build/gobackend/hideapp .

# Copy config files from build stage if they exist
COPY --from=builder /build/gobackend/configs ./configs

# Create directory for logs
RUN mkdir -p /var/log/hideapp

# Set executable permissions
RUN chmod +x /Hideme_Backend/gobackend/hideapp

# Expose the application port
EXPOSE 8080

# Run the application
CMD ["/Hideme_Backend/gobackend/hideapp"]