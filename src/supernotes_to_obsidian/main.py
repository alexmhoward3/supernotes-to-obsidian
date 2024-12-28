import asyncio
import os
from datetime import datetime
from typing import Optional
import re
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.stdio import StdioServerParameters
from . import config

class ObsidianImporter:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.template_content: Optional[str] = None
        
    async def connect(self):
        """Connect to the Obsidian MCP server"""
        server_params = StdioServerParameters(
            command="obsidian-mcp-server",
            args=[],
            env=None
        )
        
        transport = await stdio_client(server_params)
        self.session = ClientSession(transport[0], transport[1])
        await self.session.initialize()
        
    async def load_template(self):
        """Load the daily note template"""
        response = await self.session.get_file_contents(config.TEMPLATE_PATH)
        self.template_content = response
        
    def process_supernote_content(self, content: str) -> str:
        """Clean up the Supernote export content"""
        # Normalize line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove multiple empty lines
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # Add proper line breaks after sentences
        content = re.sub(r'(?<=[.!?])\s+(?=[A-Z])', '\n\n', content)
        
        # Add wikilinks around proper nouns (excluding common words and articles)
        common_words = {'The', 'A', 'An', 'This', 'That', 'These', 'Those', 'I', 'You', 'He', 'She', 'It', 'We', 'They'}
        
        words = content.split()
        processed_words = []
        for word in words:
            # Strip punctuation for checking
            clean_word = re.sub(r'[^\w\s]', '', word)
            
            # Only wikify if:
            # 1. Word starts with capital
            # 2. Not a common word
            # 3. Not all caps (likely an acronym)
            # 4. More than one letter
            if (clean_word and 
                clean_word[0].isupper() and 
                clean_word not in common_words and
                not clean_word.isupper() and 
                len(clean_word) > 1):
                # Preserve original punctuation
                punctuation = word[len(clean_word):]
                word = f"[[{clean_word}]]{punctuation}"
            processed_words.append(word)
            
        content = ' '.join(processed_words)
        
        return content.strip()
        
    async def ensure_daily_note_exists(self, date: datetime) -> str:
        """Create daily note if it doesn't exist"""
        daily_note_path = f"{config.DAILY_NOTES_FOLDER}/{date.strftime('%Y-%m-%d')}.md"
        
        try:
            # Check if file exists
            await self.session.get_file_contents(daily_note_path)
        except Exception:
            # File doesn't exist, create it from template
            if not self.template_content:
                raise ValueError("Template not loaded")
            
            # Replace template variables
            note_content = self.template_content.replace(
                "{{date}}", date.strftime("%Y-%m-%d")
            ).replace(
                "{{time}}", date.strftime("%H:%M")
            )
            
            # Create the new daily note
            await self.session.append_content(daily_note_path, note_content)
        
        return daily_note_path
        
    async def add_to_daily_note(self, note_path: str, content: str):
        """Add content to specific section in daily note"""
        try:
            # Add content under the specified section
            await self.session.patch_content(
                filepath=note_path,
                target_type="heading",
                target=config.NOTE_SECTION_HEADING,
                operation="append",
                content=f"\n{content}\n"
            )
        except Exception as e:
            print(f"Error adding content to daily note: {e}")
            
    async def process_supernote_file(self, file_path: str, date: datetime):
        """Process a single Supernote export file"""
        try:
            # Read the Supernote content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Clean up the content
            processed_content = self.process_supernote_content(content)
            
            # Ensure daily note exists
            daily_note_path = await self.ensure_daily_note_exists(date)
            
            # Add content to the daily note
            await self.add_to_daily_note(daily_note_path, processed_content)
            
            # Mark file as processed
            os.rename(file_path, file_path + config.PROCESSED_SUFFIX)
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

async def main():
    importer = ObsidianImporter()
    await importer.connect()
    
    # Load the template
    await importer.load_template()
    
    # Process all files in the export folder
    for filename in os.listdir(config.EXPORT_FOLDER):
        if (filename.endswith(config.VALID_EXTENSIONS) and 
            not filename.endswith(config.PROCESSED_SUFFIX)):
            file_path = os.path.join(config.EXPORT_FOLDER, filename)
            # You might want to extract the date from the filename or file content
            date = datetime.now()  # Replace with actual date extraction
            await importer.process_supernote_file(file_path, date)

if __name__ == "__main__":
    asyncio.run(main())