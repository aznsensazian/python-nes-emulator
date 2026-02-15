#!/bin/bash

# GitHub Repository Creation Script
# This script will help you create the GitHub repository

echo "=================================="
echo "GitHub Repository Creation Helper"
echo "=================================="
echo ""

# Check if gh CLI is available
if command -v gh &> /dev/null; then
    echo "✓ GitHub CLI (gh) detected"
    echo ""
    read -p "Do you want to create the repository using GitHub CLI? (y/n): " use_gh
    
    if [ "$use_gh" = "y" ] || [ "$use_gh" = "Y" ]; then
        echo ""
        echo "Creating repository..."
        gh repo create python-nes-emulator \
            --public \
            --description "A complete Nintendo Entertainment System (NES) emulator written in Python" \
            --source=. \
            --push
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "✅ Repository created and code pushed successfully!"
            gh repo view --web
        else
            echo ""
            echo "❌ Failed to create repository"
        fi
        exit 0
    fi
fi

# Manual instructions
echo ""
echo "GitHub CLI not available or not preferred."
echo "Please follow these manual steps:"
echo ""
echo "1. Go to: https://github.com/new"
echo "2. Repository name: python-nes-emulator"
echo "3. Description: A complete Nintendo Entertainment System (NES) emulator written in Python"
echo "4. Visibility: Public"
echo "5. Do NOT initialize with README (we have one already)"
echo "6. Click 'Create repository'"
echo ""
read -p "Press Enter after you've created the repository on GitHub..."
echo ""

# Get GitHub username
read -p "Enter your GitHub username: " github_username

if [ -z "$github_username" ]; then
    echo "❌ Username cannot be empty"
    exit 1
fi

# Add remote
echo ""
echo "Adding remote..."
git remote remove origin 2>/dev/null
git remote add origin "https://github.com/$github_username/python-nes-emulator.git"

if [ $? -eq 0 ]; then
    echo "✓ Remote added"
else
    echo "❌ Failed to add remote"
    exit 1
fi

# Push to GitHub
echo ""
echo "Pushing code to GitHub..."
echo "(You may be prompted for your GitHub credentials)"
echo ""

git branch -M main
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Code pushed successfully!"
    echo ""
    echo "Your repository is now available at:"
    echo "https://github.com/$github_username/python-nes-emulator"
    echo ""
else
    echo ""
    echo "❌ Failed to push code"
    echo ""
    echo "If you're having authentication issues:"
    echo "1. Generate a personal access token at: https://github.com/settings/tokens"
    echo "2. Use the token as your password when prompted"
    echo "3. Or set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh"
fi
