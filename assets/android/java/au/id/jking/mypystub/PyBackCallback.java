package au.id.jking.mypystub;

import androidx.activity.OnBackPressedCallback;

/**
 * An OnBackPressedCallback that asks a Handler, which Python implements.
 *
 * OnBackPressedCallback is an abstract class whose only constructor takes a
 * boolean, so Chaquopy can't extend it from Python with a static proxy (its
 * generated constructor passes no arguments). This subclass has a constructor
 * Python can call, and Python supplies the Handler interface with a dynamic proxy.
 */
public class PyBackCallback extends OnBackPressedCallback {
    /** Implemented in Python: called when Back is pressed. */
    public interface Handler {
        void handle();
    }

    private final Handler handler;

    public PyBackCallback(Handler handler) {
        super(true);
        this.handler = handler;
    }

    @Override
    public void handleOnBackPressed() {
        handler.handle();
    }
}
