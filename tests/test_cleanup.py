"""Tests for cleanup functionality using synthetic data only."""
import pytest
import sqlite3
import tempfile
from pathlib import Path
from checks.cli_history import CliHistoryCheck
from checks.logs import LogsCheck
from checks.desktop_database import DesktopDatabaseCheck
from checks.saved_models import SavedModelsCheck
from checks.context import ScanContext, AccountContext


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_context(temp_dir):
    return ScanContext(
        accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
        environment_sources={},
        model_directories=[],
        log_directories=[],
        redirected_logs=[],
        model_source_paths=[]
    )


class TestCliHistoryCleanup:
    def test_plan_finds_history_file(self, sample_context, temp_dir):
        history_file = temp_dir / '.ollama' / 'history'
        history_file.parent.mkdir(parents=True)
        history_file.write_text('prompt1\nprompt2\n')
        
        checker = CliHistoryCheck()
        plan = checker.plan(sample_context)
        
        assert plan.cleanup_available is True
        assert len(plan.findings['targets']) == 1
        assert plan.findings['targets'][0]['path'] == str(history_file)
    
    def test_plan_empty_when_no_history(self, sample_context, temp_dir):
        checker = CliHistoryCheck()
        plan = checker.plan(sample_context)
        
        assert plan.cleanup_available is False
        assert len(plan.findings['targets']) == 0
    
    def test_execute_deletes_file(self, sample_context, temp_dir):
        history_file = temp_dir / '.ollama' / 'history'
        history_file.parent.mkdir(parents=True)
        history_file.write_text('prompt1\nprompt2\n')
        
        checker = CliHistoryCheck()
        plan = checker.plan(sample_context)
        result = checker.execute(sample_context, plan, confirmed=True)
        
        assert len(result['deleted']) == 1
        assert not history_file.exists()
    
    def test_execute_requires_confirmation(self, sample_context, temp_dir):
        history_file = temp_dir / '.ollama' / 'history'
        history_file.parent.mkdir(parents=True)
        history_file.write_text('prompt1\n')
        
        checker = CliHistoryCheck()
        plan = checker.plan(sample_context)
        
        with pytest.raises(ValueError, match='Confirmation required'):
            checker.execute(sample_context, plan, confirmed=False)
    
    def test_verify_after_cleanup(self, sample_context, temp_dir):
        history_file = temp_dir / '.ollama' / 'history'
        history_file.parent.mkdir(parents=True)
        history_file.write_text('prompt1\n')
        
        checker = CliHistoryCheck()
        plan = checker.plan(sample_context)
        checker.execute(sample_context, plan, confirmed=True)
        verification = checker.verify(sample_context)
        
        assert verification.findings['history_files_found'] == 0


class TestLogsCleanup:
    def test_plan_finds_log_files(self, sample_context, temp_dir):
        log_dir = temp_dir / 'logs'
        log_dir.mkdir()
        (log_dir / 'server.log').write_text('log line 1\n')
        (log_dir / 'server-1.log').write_text('old log\n')
        
        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir)],
            environment_sources={},
            log_directories=[log_dir],
            redirected_logs=[],
            model_source_paths=[]
        )
        
        checker = LogsCheck()
        plan = checker.plan(context)
        
        assert plan.cleanup_available is True
        assert len(plan.findings['targets']) == 2
    
    def test_execute_deletes_logs(self, sample_context, temp_dir):
        log_dir = temp_dir / 'logs'
        log_dir.mkdir()
        log_file = log_dir / 'server.log'
        log_file.write_text('log line 1\n')
        
        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir)],
            environment_sources={},
            log_directories=[log_dir],
            redirected_logs=[],
            model_source_paths=[]
        )
        
        checker = LogsCheck()
        plan = checker.plan(context)
        result = checker.execute(sample_context, plan, confirmed=True)
        
        assert len(result['deleted']) == 1
        assert not log_file.exists()


class TestDesktopDatabaseCleanup:
    def test_plan_finds_database_with_chats(self, sample_context, temp_dir):
        # Desktop database checker expects local_app_data on Windows
        ollama_dir = temp_dir / 'Ollama'
        ollama_dir.mkdir()
        db_file = ollama_dir / 'db.sqlite'
        conn = sqlite3.connect(str(db_file))
        conn.execute('CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)')
        conn.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)')
        conn.execute('INSERT INTO chats (title) VALUES (?)', ('Test Chat',))
        conn.execute('INSERT INTO messages (content) VALUES (?)', ('Test message',))
        conn.commit()
        conn.close()

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = DesktopDatabaseCheck()
        plan = checker.plan(context)

        assert plan.cleanup_available is True
        assert len(plan.findings['targets']) == 1
        assert plan.findings['targets'][0]['chats'] == 1
        assert plan.findings['targets'][0]['messages'] == 1
    
    def test_execute_deletes_rows(self, sample_context, temp_dir):
        # Desktop database checker expects local_app_data on Windows
        ollama_dir = temp_dir / 'Ollama'
        ollama_dir.mkdir()
        db_file = ollama_dir / 'db.sqlite'
        conn = sqlite3.connect(str(db_file))
        conn.execute('CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)')
        conn.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)')
        conn.execute('CREATE TABLE attachments (id INTEGER PRIMARY KEY, data BLOB)')
        conn.execute('CREATE TABLE tool_calls (id INTEGER PRIMARY KEY, args TEXT)')
        conn.execute('INSERT INTO chats (title) VALUES (?)', ('Test Chat',))
        conn.execute('INSERT INTO messages (content) VALUES (?)', ('Test message',))
        conn.commit()
        conn.close()

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = DesktopDatabaseCheck()
        plan = checker.plan(context)
        result = checker.execute(context, plan, confirmed=True)

        assert len(result['deleted']) == 1
        assert result['deleted'][0]['chats_deleted'] == 1
        assert result['deleted'][0]['messages_deleted'] == 1

        # Verify deletion
        conn = sqlite3.connect(str(db_file))
        chats = conn.execute('SELECT COUNT(*) FROM chats').fetchone()[0]
        messages = conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        conn.close()
        assert chats == 0
        assert messages == 0

    def test_plan_is_read_only(self, sample_context, temp_dir):
        """plan() must not create WAL/SHM/journal companions or modify the DB."""
        ollama_dir = temp_dir / 'Ollama'
        ollama_dir.mkdir()
        db_file = ollama_dir / 'db.sqlite'
        conn = sqlite3.connect(str(db_file))
        conn.execute('CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)')
        conn.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)')
        conn.execute('INSERT INTO chats (title) VALUES (?)', ('Test Chat',))
        conn.commit()
        conn.close()

        before = db_file.read_bytes()
        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = DesktopDatabaseCheck()
        plan = checker.plan(context)

        assert plan.cleanup_available is True
        assert db_file.read_bytes() == before
        for suffix in ('-wal', '-shm', '-journal'):
            assert not (ollama_dir / ('db.sqlite' + suffix)).exists()

    def test_plan_fails_closed_on_unexpected_schema(self, sample_context, temp_dir):
        """A database without the expected tables must produce no cleanup targets."""
        ollama_dir = temp_dir / 'Ollama'
        ollama_dir.mkdir()
        db_file = ollama_dir / 'db.sqlite'
        conn = sqlite3.connect(str(db_file))
        conn.execute('CREATE TABLE unrelated (id INTEGER PRIMARY KEY, data TEXT)')
        conn.execute("INSERT INTO unrelated (data) VALUES ('not a chat')")
        conn.commit()
        conn.close()

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = DesktopDatabaseCheck()
        plan = checker.plan(context)

        assert plan.cleanup_available is False
        assert plan.findings['targets'] == []


class TestSavedModelsCleanup:
    def test_plan_finds_message_layer_manifests(self, sample_context, temp_dir):
        import json
        import hashlib
        # Saved models checker expects .ollama/models in home directory
        models_dir = temp_dir / '.ollama' / 'models'
        manifests_dir = models_dir / 'manifests'
        blobs_dir = models_dir / 'blobs'
        manifests_dir.mkdir(parents=True)
        blobs_dir.mkdir(parents=True)

        # Use valid 64-character SHA-256 digests
        weight_digest = 'sha256:' + hashlib.sha256(b'weight').hexdigest()
        message_digest = 'sha256:' + hashlib.sha256(b'message').hexdigest()

        manifest = {
            'schemaVersion': 2,
            'layers': [
                {'digest': weight_digest, 'mediaType': 'application/vnd.ollama.image.model'},
                {'digest': message_digest, 'mediaType': 'application/vnd.ollama.image.messages'}
            ]
        }
        manifest_file = manifests_dir / 'test-manifest.json'
        manifest_file.write_text(json.dumps(manifest))

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = SavedModelsCheck()
        plan = checker.plan(context)

        assert plan.cleanup_available is True
        assert len(plan.findings['targets']) == 1
    
    def test_execute_deletes_manifest_and_blobs(self, sample_context, temp_dir):
        import json
        import hashlib
        # Saved models checker expects .ollama/models in home directory
        models_dir = temp_dir / '.ollama' / 'models'
        manifests_dir = models_dir / 'manifests'
        blobs_dir = models_dir / 'blobs'
        manifests_dir.mkdir(parents=True)
        blobs_dir.mkdir(parents=True)

        # Use valid 64-character SHA-256 digests
        weight_digest = 'sha256:' + hashlib.sha256(b'weight').hexdigest()
        message_digest = 'sha256:' + hashlib.sha256(b'message').hexdigest()
        blob_filename = message_digest.replace(':', '-')
        blob_file = blobs_dir / blob_filename
        blob_file.write_text('blob content')

        manifest = {
            'schemaVersion': 2,
            'layers': [
                {'digest': weight_digest, 'mediaType': 'application/vnd.ollama.image.model'},
                {'digest': message_digest, 'mediaType': 'application/vnd.ollama.image.messages'}
            ]
        }
        manifest_file = manifests_dir / 'test-manifest.json'
        manifest_file.write_text(json.dumps(manifest))

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = SavedModelsCheck()
        plan = checker.plan(context)
        result = checker.execute(context, plan, confirmed=True)

        assert len(result['deleted']) == 1
        assert not manifest_file.exists()
        assert not blob_file.exists()

    @pytest.mark.parametrize("digest,should_reject", [
        ("sha256:abc", True),  # Too short
        ("sha256:abc123" + "x" * 58, True),  # Too long (65 chars after colon)
        ("sha256:gggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggg", True),  # Non-hex
        ("sha256:../../etc/passwd", True),  # Path traversal attempt
        ("sha256:" + "a" * 64, False),  # Valid hex
    ])
    def test_invalid_digests_are_rejected(self, sample_context, temp_dir, digest, should_reject):
        """Test that invalid digests are rejected and never used to build paths."""
        import json
        models_dir = temp_dir / '.ollama' / 'models'
        manifests_dir = models_dir / 'manifests'
        blobs_dir = models_dir / 'blobs'
        manifests_dir.mkdir(parents=True)
        blobs_dir.mkdir(parents=True)

        manifest = {
            'schemaVersion': 2,
            'layers': [
                {'digest': digest, 'mediaType': 'application/vnd.ollama.image.messages'}
            ]
        }
        manifest_file = manifests_dir / 'test-manifest.json'
        manifest_file.write_text(json.dumps(manifest))

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        checker = SavedModelsCheck()
        plan = checker.plan(context)

        # Invalid digests should result in no targets
        if should_reject:
            assert plan.cleanup_available is False
            assert len(plan.findings['targets']) == 0
        else:
            # Valid digest should be detected
            assert plan.cleanup_available is True
            assert len(plan.findings['targets']) == 1


class TestGeneralCleanupExcludesModels:
    """Test that general cleanup (CLI history, logs, database) does not touch models directory."""
    def test_cli_history_cleanup_leaves_models_untouched(self, sample_context, temp_dir):
        import json
        # Create a models directory with content (explicit path for test)
        models_dir = temp_dir / 'models'
        manifests_dir = models_dir / 'manifests'
        blobs_dir = models_dir / 'blobs'
        manifests_dir.mkdir(parents=True)
        blobs_dir.mkdir(parents=True)

        # Add a manifest and blob
        manifest_file = manifests_dir / 'test-manifest.json'
        manifest_file.write_text(json.dumps({'schemaVersion': 2, 'layers': []}))
        blob_file = blobs_dir / 'sha256-test'
        blob_file.write_text('blob content')

        # Also create CLI history
        history_file = temp_dir / '.ollama' / 'history'
        history_file.parent.mkdir(parents=True)
        history_file.write_text('prompt1\n')

        # Run CLI history cleanup - use same context for both
        checker = CliHistoryCheck()
        plan = checker.plan(sample_context)
        result = checker.execute(sample_context, plan, confirmed=True)

        # Verify history deleted but models untouched
        assert len(result['deleted']) == 1
        assert not history_file.exists()
        assert manifest_file.exists()
        assert blob_file.exists()

    def test_logs_cleanup_leaves_models_untouched(self, sample_context, temp_dir):
        import json
        # Create a models directory with content (explicit path for test)
        models_dir = temp_dir / 'models'
        manifests_dir = models_dir / 'manifests'
        blobs_dir = models_dir / 'blobs'
        manifests_dir.mkdir(parents=True)
        blobs_dir.mkdir(parents=True)

        manifest_file = manifests_dir / 'test-manifest.json'
        manifest_file.write_text(json.dumps({'schemaVersion': 2, 'layers': []}))
        blob_file = blobs_dir / 'sha256-test'
        blob_file.write_text('blob content')

        # Also create log file - use redirected_logs for simplicity
        log_file = temp_dir / 'test.log'
        log_file.write_text('log line 1\n')

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[models_dir],
            log_directories=[],
            redirected_logs=[str(log_file)],
            model_source_paths=[]
        )

        # Run logs cleanup - use same context for both
        checker = LogsCheck()
        plan = checker.plan(context)
        result = checker.execute(context, plan, confirmed=True)

        # Verify logs deleted but models untouched
        assert len(result['deleted']) == 1
        assert not log_file.exists()
        assert manifest_file.exists()
        assert blob_file.exists()

    def test_database_cleanup_leaves_models_untouched(self, sample_context, temp_dir):
        import json
        # Create a models directory with content (explicit path for test)
        models_dir = temp_dir / 'models'
        manifests_dir = models_dir / 'manifests'
        blobs_dir = models_dir / 'blobs'
        manifests_dir.mkdir(parents=True)
        blobs_dir.mkdir(parents=True)

        manifest_file = manifests_dir / 'test-manifest.json'
        manifest_file.write_text(json.dumps({'schemaVersion': 2, 'layers': []}))
        blob_file = blobs_dir / 'sha256-test'
        blob_file.write_text('blob content')

        # Also create database in local_app_data location
        ollama_dir = temp_dir / 'Ollama'
        ollama_dir.mkdir()
        db_file = ollama_dir / 'db.sqlite'
        conn = sqlite3.connect(str(db_file))
        conn.execute('CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)')
        conn.execute('INSERT INTO chats (title) VALUES (?)', ('Test Chat',))
        conn.commit()
        conn.close()

        context = ScanContext(
            accounts=[AccountContext('test_user', temp_dir, temp_dir, platform='win32')],
            environment_sources={},
            model_directories=[models_dir],
            log_directories=[],
            redirected_logs=[],
            model_source_paths=[]
        )

        # Run database cleanup - use same context for both
        checker = DesktopDatabaseCheck()
        plan = checker.plan(context)

        # If plan found targets, execute and verify
        if plan.cleanup_available:
            result = checker.execute(context, plan, confirmed=True)
            assert len(result['deleted']) == 1
            # Verify database was cleaned
            conn = sqlite3.connect(str(db_file))
            chats = conn.execute('SELECT COUNT(*) FROM chats').fetchone()[0]
            conn.close()
            assert chats == 0

        # Regardless of plan success, verify models untouched
        assert manifest_file.exists()
        assert blob_file.exists()
