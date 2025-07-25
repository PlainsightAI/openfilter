#!/usr/bin/env python3
"""
Test GCS connectivity and list images from the specified bucket.
"""

import os
from google.cloud import storage

def test_gcs_connection():
    """Test GCS connection and list images from the specified bucket."""
    try:
        # Initialize the client
        client = storage.Client()
        print("✅ GCS client initialized successfully")
        
        # Test with your specific bucket and path
        bucket_name = "protege-artifacts-development"
        prefix = "labelled-data/demo_ocr/data"
        
        print(f"🔍 Listing images from gs://{bucket_name}/{prefix}")
        
        # Get the bucket
        bucket = client.bucket(bucket_name)
        
        # List blobs with the prefix
        blobs = bucket.list_blobs(prefix=prefix)
        
        # Filter for image files
        image_extensions = {'jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff', 'gif', 'webp'}
        image_files = []
        
        for blob in blobs:
            # Check if it's an image file
            ext = blob.name.lower().rsplit(".", 1)[-1] if "." in blob.name else ""
            if ext in image_extensions:
                image_files.append(blob.name)
                print(f"  📸 Found image: {blob.name}")
        
        print(f"\n✅ Successfully found {len(image_files)} image files")
        
        if image_files:
            print("\nFirst few images:")
            for i, img in enumerate(image_files[:5]):
                print(f"  {i+1}. {img}")
            if len(image_files) > 5:
                print(f"  ... and {len(image_files) - 5} more")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing GCS Connection...")
    print("=" * 40)
    
    success = test_gcs_connection()
    
    if success:
        print("\n🎉 GCS connection successful! You can now use gs:// paths in ImageIn filter.")
    else:
        print("\n💡 If you're still having issues, try:")
        print("   1. Run: gcloud auth application-default login")
        print("   2. Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
        print("   3. Check your Google Cloud project permissions") 