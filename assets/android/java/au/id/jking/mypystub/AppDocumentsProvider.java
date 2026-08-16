package au.id.jking.mypystub;

import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.provider.DocumentsProvider;
import android.webkit.MimeTypeMap;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

public class AppDocumentsProvider extends DocumentsProvider {
    private static final String DEFAULT_ROOT_ID = "app_documents_root";

    private static final String[] DEFAULT_ROOT_PROJECTION = new String[]{
        Root.COLUMN_ROOT_ID,
        Root.COLUMN_FLAGS,
        Root.COLUMN_TITLE,
        Root.COLUMN_DOCUMENT_ID,
        Root.COLUMN_ICON,
    };

    private static final String[] DEFAULT_DOCUMENT_PROJECTION = new String[]{
        Document.COLUMN_DOCUMENT_ID,
        Document.COLUMN_MIME_TYPE,
        Document.COLUMN_DISPLAY_NAME,
        Document.COLUMN_LAST_MODIFIED,
        Document.COLUMN_FLAGS,
        Document.COLUMN_SIZE,
    };

    /**
     * Maps to app.paths.documents.
     * Uses getFilesDir() directly (or getExternalFilesDir("Documents") if preferred).
     */
    private File getBaseDir() {
        File baseDir = getContext().getFilesDir();
        if (!baseDir.exists()) {
            baseDir.mkdirs();
        }
        return baseDir;
    }

    @Override
    public boolean onCreate() {
        getBaseDir();
        return true;
    }

    @Override
    public Cursor queryRoots(String[] projection) throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_ROOT_PROJECTION);
        File baseDir = getBaseDir();

        MatrixCursor.RowBuilder row = result.newRow();
        row.add(Root.COLUMN_ROOT_ID, DEFAULT_ROOT_ID);
        row.add(Root.COLUMN_DOCUMENT_ID, baseDir.getAbsolutePath());
        row.add(Root.COLUMN_TITLE, "My Py Stub"); // Your formal app name
        
        // Critical flags required for ChromeOS Files drag-and-drop & folder creation
        row.add(Root.COLUMN_FLAGS, 
            Root.FLAG_SUPPORTS_CREATE | 
            Root.FLAG_SUPPORTS_SEARCH | 
            Root.FLAG_SUPPORTS_IS_CHILD
        );
        row.add(Root.COLUMN_ICON, R.mipmap.ic_launcher);

        return result;
    }

    @Override
    public Cursor queryDocument(String documentId, String[] projection) throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        includeFile(result, new File(documentId));
        return result;
    }

    @Override
    public Cursor queryChildDocuments(String parentDocumentId, String[] projection, String sortOrder) throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        File parent = new File(parentDocumentId);
        File[] files = parent.listFiles();
        if (files != null) {
            for (File file : files) {
                includeFile(result, file);
            }
        }
        return result;
    }

    @Override
    public ParcelFileDescriptor openDocument(String documentId, String mode, CancellationSignal signal) throws FileNotFoundException {
        File file = new File(documentId);
        int accessMode = ParcelFileDescriptor.parseMode(mode);
        return ParcelFileDescriptor.open(file, accessMode);
    }

    // =========================================================================
    // WRITE / DRAG-AND-DROP HANDLERS (Required for file copying & edits)
    // =========================================================================

    @Override
    public String createDocument(String parentDocumentId, String mimeType, String displayName) throws FileNotFoundException {
        File parent = new File(parentDocumentId);
        File file = new File(parent, displayName);

        try {
            if (Document.MIME_TYPE_DIR.equals(mimeType)) {
                if (!file.mkdir()) {
                    throw new FileNotFoundException("Failed to create directory: " + file.getAbsolutePath());
                }
            } else {
                if (!file.createNewFile()) {
                    throw new FileNotFoundException("Failed to create file: " + file.getAbsolutePath());
                }
            }
        } catch (IOException e) {
            throw new FileNotFoundException("Failed to create document: " + e.getMessage());
        }

        return file.getAbsolutePath();
    }

    @Override
    public void deleteDocument(String documentId) throws FileNotFoundException {
        File file = new File(documentId);
        if (file.exists()) {
            if (!file.delete()) {
                throw new FileNotFoundException("Failed to delete file: " + documentId);
            }
        }
    }

    private void includeFile(MatrixCursor result, File file) {
        MatrixCursor.RowBuilder row = result.newRow();
        row.add(Document.COLUMN_DOCUMENT_ID, file.getAbsolutePath());
        row.add(Document.COLUMN_DISPLAY_NAME, file.getName());
        row.add(Document.COLUMN_SIZE, file.length());
        row.add(Document.COLUMN_LAST_MODIFIED, file.lastModified());

        int flags = Document.FLAG_SUPPORTS_DELETE | Document.FLAG_SUPPORTS_WRITE;

        if (file.isDirectory()) {
            row.add(Document.COLUMN_MIME_TYPE, Document.MIME_TYPE_DIR);
            row.add(Document.COLUMN_FLAGS, flags | Document.FLAG_DIR_SUPPORTS_CREATE);
        } else {
            row.add(Document.COLUMN_MIME_TYPE, getTypeForFile(file));
            row.add(Document.COLUMN_FLAGS, flags);
        }
    }

    private String getTypeForFile(File file) {
        String name = file.getName();
        int lastDot = name.lastIndexOf('.');
        if (lastDot >= 0) {
            String extension = name.substring(lastDot + 1).toLowerCase();
            String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
            if (mime != null) return mime;
        }
        return "application/octet-stream";
    }
}