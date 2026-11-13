package au.id.jking.mypystub;

import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.provider.DocumentsProvider;
import android.webkit.MimeTypeMap;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

/**
 * Shows the app's documents folder (Context.getFilesDir(), the folder the
 * launcher lists as Documents) in the system Files browser and file pickers.
 *
 * Document IDs are "root" for the folder itself and "root/<relative path>" for
 * what is inside it, never raw absolute paths, and every ID is checked to stay
 * inside the folder. Only the flags whose methods are implemented here are
 * advertised: the framework's defaults throw for the rest (search, rename,
 * copy, move), and a file browser that calls one then crashes.
 */
public class AppDocumentsProvider extends DocumentsProvider {
    /** Must match android:authorities in pyproject.toml and files_app.py. */
    public static final String AUTHORITY = "au.id.jking.mypystub.documents";
    public static final String ROOT_ID = "mypystub";
    public static final String ROOT_DOC_ID = "root";

    private static final int MAX_SEARCH_RESULTS = 50;

    private static final String[] DEFAULT_ROOT_PROJECTION = new String[]{
        Root.COLUMN_ROOT_ID,
        Root.COLUMN_FLAGS,
        Root.COLUMN_TITLE,
        Root.COLUMN_DOCUMENT_ID,
        Root.COLUMN_ICON,
        Root.COLUMN_MIME_TYPES,
        Root.COLUMN_AVAILABLE_BYTES,
    };

    private static final String[] DEFAULT_DOCUMENT_PROJECTION = new String[]{
        Document.COLUMN_DOCUMENT_ID,
        Document.COLUMN_MIME_TYPE,
        Document.COLUMN_DISPLAY_NAME,
        Document.COLUMN_LAST_MODIFIED,
        Document.COLUMN_FLAGS,
        Document.COLUMN_SIZE,
    };

    // -- Locating files -----------------------------------------------------

    private File baseDir() {
        File base = getContext().getFilesDir();
        if (!base.exists()) {
            base.mkdirs();
        }
        return base;
    }

    /** The file for a document ID, refusing anything outside the folder. */
    private File fileFor(String documentId) throws FileNotFoundException {
        File base = baseDir();
        File file;
        if (ROOT_DOC_ID.equals(documentId)) {
            file = base;
        } else if (documentId != null && documentId.startsWith(ROOT_DOC_ID + "/")) {
            file = new File(base, documentId.substring(ROOT_DOC_ID.length() + 1));
        } else {
            throw new FileNotFoundException("Unknown document: " + documentId);
        }
        if (!inside(base, file)) {
            throw new FileNotFoundException("Outside the documents folder: " + documentId);
        }
        return file;
    }

    /** The document ID of a file inside the folder. */
    private String idFor(File file) throws FileNotFoundException {
        File base = baseDir();
        try {
            String basePath = base.getCanonicalPath();
            String path = file.getCanonicalPath();
            if (path.equals(basePath)) {
                return ROOT_DOC_ID;
            }
            if (path.startsWith(basePath + File.separator)) {
                return ROOT_DOC_ID + "/" + path.substring(basePath.length() + 1);
            }
        } catch (IOException e) {
            throw new FileNotFoundException(e.getMessage());
        }
        throw new FileNotFoundException("Outside the documents folder: " + file);
    }

    private static boolean inside(File base, File file) {
        try {
            String basePath = base.getCanonicalPath();
            String path = file.getCanonicalPath();
            return path.equals(basePath) || path.startsWith(basePath + File.separator);
        } catch (IOException e) {
            return false;
        }
    }

    private void notifyChildrenChanged(File folder) {
        try {
            Uri uri = DocumentsContract.buildChildDocumentsUri(AUTHORITY, idFor(folder));
            getContext().getContentResolver().notifyChange(uri, null);
        } catch (FileNotFoundException e) {
            // Outside the folder: nothing of ours to refresh
        }
    }

    // -- Reading --------------------------------------------------------------

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public Cursor queryRoots(String[] projection) throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_ROOT_PROJECTION);
        MatrixCursor.RowBuilder row = result.newRow();
        row.add(Root.COLUMN_ROOT_ID, ROOT_ID);
        row.add(Root.COLUMN_DOCUMENT_ID, ROOT_DOC_ID);
        row.add(Root.COLUMN_TITLE, "MyPyStub");
        row.add(Root.COLUMN_FLAGS,
            Root.FLAG_SUPPORTS_CREATE
                | Root.FLAG_SUPPORTS_SEARCH
                | Root.FLAG_SUPPORTS_IS_CHILD
                | Root.FLAG_LOCAL_ONLY);
        row.add(Root.COLUMN_ICON, R.mipmap.ic_launcher);
        row.add(Root.COLUMN_MIME_TYPES, "*/*");
        row.add(Root.COLUMN_AVAILABLE_BYTES, baseDir().getFreeSpace());
        return result;
    }

    @Override
    public Cursor queryDocument(String documentId, String[] projection) throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        includeFile(result, fileFor(documentId));
        return result;
    }

    @Override
    public Cursor queryChildDocuments(String parentDocumentId, String[] projection, String sortOrder)
            throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        File parent = fileFor(parentDocumentId);
        File[] files = parent.listFiles();
        if (files != null) {
            for (File file : files) {
                includeFile(result, file);
            }
        }
        // Lets an open listing refresh when something here changes
        result.setNotificationUri(
            getContext().getContentResolver(),
            DocumentsContract.buildChildDocumentsUri(AUTHORITY, parentDocumentId));
        return result;
    }

    @Override
    public Cursor querySearchDocuments(String rootId, String query, String[] projection)
            throws FileNotFoundException {
        MatrixCursor result = new MatrixCursor(projection != null ? projection : DEFAULT_DOCUMENT_PROJECTION);
        String needle = query == null ? "" : query.toLowerCase(Locale.ROOT);
        Deque<File> pending = new ArrayDeque<>();
        pending.add(baseDir());
        while (!pending.isEmpty() && result.getCount() < MAX_SEARCH_RESULTS) {
            File[] files = pending.removeFirst().listFiles();
            if (files == null) {
                continue;
            }
            for (File file : files) {
                if (file.getName().toLowerCase(Locale.ROOT).contains(needle)) {
                    includeFile(result, file);
                    if (result.getCount() >= MAX_SEARCH_RESULTS) {
                        break;
                    }
                }
                if (file.isDirectory()) {
                    pending.add(file);
                }
            }
        }
        return result;
    }

    @Override
    public boolean isChildDocument(String parentDocumentId, String documentId) {
        try {
            File parent = fileFor(parentDocumentId);
            File child = fileFor(documentId);
            return inside(parent, child);
        } catch (FileNotFoundException e) {
            return false;
        }
    }

    @Override
    public ParcelFileDescriptor openDocument(String documentId, String mode, CancellationSignal signal)
            throws FileNotFoundException {
        final File file = fileFor(documentId);
        int accessMode = ParcelFileDescriptor.parseMode(mode);
        if (mode.indexOf('w') < 0) {
            return ParcelFileDescriptor.open(file, accessMode);
        }
        // Written: tell open listings once the writer is done (new size, time)
        try {
            Handler handler = new Handler(Looper.getMainLooper());
            return ParcelFileDescriptor.open(file, accessMode, handler,
                e -> notifyChildrenChanged(file.getParentFile()));
        } catch (IOException e) {
            throw new FileNotFoundException(e.getMessage());
        }
    }

    // -- Writing --------------------------------------------------------------

    @Override
    public String createDocument(String parentDocumentId, String mimeType, String displayName)
            throws FileNotFoundException {
        File parent = fileFor(parentDocumentId);
        File file = freeName(parent, displayName);
        try {
            boolean made = Document.MIME_TYPE_DIR.equals(mimeType) ? file.mkdir() : file.createNewFile();
            if (!made) {
                throw new FileNotFoundException("Couldn't create " + file.getName());
            }
        } catch (IOException e) {
            throw new FileNotFoundException("Couldn't create " + file.getName() + ": " + e.getMessage());
        }
        notifyChildrenChanged(parent);
        return idFor(file);
    }

    @Override
    public String renameDocument(String documentId, String displayName) throws FileNotFoundException {
        File file = fileFor(documentId);
        if (ROOT_DOC_ID.equals(documentId)) {
            throw new FileNotFoundException("The documents folder can't be renamed");
        }
        File target = freeName(file.getParentFile(), displayName);
        if (!file.renameTo(target)) {
            throw new FileNotFoundException("Couldn't rename " + file.getName());
        }
        notifyChildrenChanged(file.getParentFile());
        return idFor(target);
    }

    @Override
    public void deleteDocument(String documentId) throws FileNotFoundException {
        if (ROOT_DOC_ID.equals(documentId)) {
            throw new FileNotFoundException("The documents folder can't be deleted");
        }
        File file = fileFor(documentId);
        if (!deleteAll(file)) {
            throw new FileNotFoundException("Couldn't delete " + file.getName());
        }
        notifyChildrenChanged(file.getParentFile());
    }

    @Override
    public String copyDocument(String sourceDocumentId, String targetParentDocumentId)
            throws FileNotFoundException {
        File source = fileFor(sourceDocumentId);
        File parent = fileFor(targetParentDocumentId);
        if (inside(source, parent)) {
            throw new FileNotFoundException("Can't copy a folder into itself");
        }
        File target = freeName(parent, source.getName());
        try {
            copyAll(source, target);
        } catch (IOException e) {
            throw new FileNotFoundException("Couldn't copy " + source.getName() + ": " + e.getMessage());
        }
        notifyChildrenChanged(parent);
        return idFor(target);
    }

    @Override
    public String moveDocument(String sourceDocumentId, String sourceParentDocumentId,
            String targetParentDocumentId) throws FileNotFoundException {
        File source = fileFor(sourceDocumentId);
        File parent = fileFor(targetParentDocumentId);
        if (ROOT_DOC_ID.equals(sourceDocumentId) || inside(source, parent)) {
            throw new FileNotFoundException("Can't move a folder into itself");
        }
        File target = freeName(parent, source.getName());
        if (!source.renameTo(target)) {
            throw new FileNotFoundException("Couldn't move " + source.getName());
        }
        notifyChildrenChanged(source.getParentFile());
        notifyChildrenChanged(parent);
        return idFor(target);
    }

    // -- Helpers --------------------------------------------------------------

    /** `name` in `parent`, or "name (2).ext", "name (3).ext"... if it is taken. */
    private static File freeName(File parent, String name) throws FileNotFoundException {
        if (name == null || name.isEmpty() || name.contains("/") || name.equals(".") || name.equals("..")) {
            throw new FileNotFoundException("Not a usable name: " + name);
        }
        File file = new File(parent, name);
        int dot = name.lastIndexOf('.');
        String stem = dot > 0 ? name.substring(0, dot) : name;
        String ext = dot > 0 ? name.substring(dot) : "";
        for (int n = 2; file.exists(); n++) {
            file = new File(parent, stem + " (" + n + ")" + ext);
        }
        return file;
    }

    private static boolean deleteAll(File file) {
        File[] children = file.isDirectory() ? file.listFiles() : null;
        if (children != null) {
            for (File child : children) {
                if (!deleteAll(child)) {
                    return false;
                }
            }
        }
        return file.delete();
    }

    private static void copyAll(File source, File target) throws IOException {
        if (source.isDirectory()) {
            if (!target.mkdir()) {
                throw new IOException("Couldn't create " + target.getName());
            }
            File[] children = source.listFiles();
            if (children != null) {
                for (File child : children) {
                    copyAll(child, new File(target, child.getName()));
                }
            }
            return;
        }
        try (InputStream in = new FileInputStream(source); OutputStream out = new FileOutputStream(target)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
        }
    }

    private void includeFile(MatrixCursor result, File file) throws FileNotFoundException {
        MatrixCursor.RowBuilder row = result.newRow();
        String id = idFor(file);
        row.add(Document.COLUMN_DOCUMENT_ID, id);
        row.add(Document.COLUMN_DISPLAY_NAME, ROOT_DOC_ID.equals(id) ? "MyPyStub" : file.getName());
        row.add(Document.COLUMN_SIZE, file.isDirectory() ? null : file.length());
        row.add(Document.COLUMN_LAST_MODIFIED, file.lastModified());

        int flags = Document.FLAG_SUPPORTS_WRITE;
        if (!ROOT_DOC_ID.equals(id)) {
            flags |= Document.FLAG_SUPPORTS_DELETE
                | Document.FLAG_SUPPORTS_RENAME
                | Document.FLAG_SUPPORTS_COPY
                | Document.FLAG_SUPPORTS_MOVE;
        }
        if (file.isDirectory()) {
            row.add(Document.COLUMN_MIME_TYPE, Document.MIME_TYPE_DIR);
            row.add(Document.COLUMN_FLAGS, (flags & ~Document.FLAG_SUPPORTS_WRITE) | Document.FLAG_DIR_SUPPORTS_CREATE);
        } else {
            row.add(Document.COLUMN_MIME_TYPE, typeFor(file));
            row.add(Document.COLUMN_FLAGS, flags);
        }
    }

    private static String typeFor(File file) {
        String name = file.getName();
        int dot = name.lastIndexOf('.');
        if (dot >= 0) {
            String extension = name.substring(dot + 1).toLowerCase(Locale.ROOT);
            if (extension.equals("py") || extension.equals("pyw")) {
                return "text/x-python";
            }
            String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
            if (mime != null) {
                return mime;
            }
        }
        return "application/octet-stream";
    }
}
