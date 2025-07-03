
#!/bin/bash

# Labl IQ Rate Analyzer - Deployment Script
# This script helps automate the deployment process

set -e  # Exit on any error

echo "🚀 Labl IQ Rate Analyzer Deployment Script"
echo "==========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if required files exist
check_requirements() {
    echo "🔍 Checking deployment requirements..."
    
    if [ ! -f "Dockerfile" ]; then
        print_error "Dockerfile not found!"
        exit 1
    fi
    
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found!"
        exit 1
    fi
    
    if [ ! -f "prisma/schema.prisma" ]; then
        print_error "Prisma schema not found!"
        exit 1
    fi
    
    print_status "All required files found"
}

# Test Docker build
test_docker_build() {
    echo "🐳 Testing Docker build..."
    
    if docker build -t labl-iq-test . > /dev/null 2>&1; then
        print_status "Docker build successful"
        docker rmi labl-iq-test > /dev/null 2>&1
    else
        print_error "Docker build failed!"
        echo "Run 'docker build -t labl-iq-test .' to see detailed error"
        exit 1
    fi
}

# Generate Prisma client
generate_prisma() {
    echo "🔧 Generating Prisma client..."
    
    if command -v prisma &> /dev/null; then
        prisma generate
        print_status "Prisma client generated"
    else
        print_warning "Prisma CLI not found, skipping client generation"
        print_warning "Make sure to run 'prisma generate' in production"
    fi
}

# Check environment variables
check_env_vars() {
    echo "🔐 Checking environment variables..."
    
    if [ ! -f ".env.production.example" ]; then
        print_error ".env.production.example not found!"
        exit 1
    fi
    
    print_status "Environment template found"
    print_warning "Make sure to set all required environment variables in production:"
    echo "  - DATABASE_URL"
    echo "  - SECRET_KEY"
    echo "  - REFRESH_SECRET_KEY"
    echo "  - CORS_ORIGINS"
}

# Main deployment preparation
main() {
    echo "Starting deployment preparation..."
    echo ""
    
    check_requirements
    echo ""
    
    test_docker_build
    echo ""
    
    generate_prisma
    echo ""
    
    check_env_vars
    echo ""
    
    print_status "Deployment preparation complete!"
    echo ""
    echo "📋 Next steps:"
    echo "1. Push your code to GitHub"
    echo "2. Deploy to Railway or Render"
    echo "3. Set up PostgreSQL database"
    echo "4. Configure environment variables"
    echo "5. Run database migrations"
    echo "6. Create admin user with seed script"
    echo ""
    echo "📖 See DEPLOYMENT_GUIDE.md for detailed instructions"
}

# Run main function
main
