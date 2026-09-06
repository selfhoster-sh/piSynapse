package com.pisynapse.app;

import android.content.ComponentCallbacks2;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    {
        initialPlugins.add(PiSynapseBridge.class);
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        // The litert model holds ~2.5GB native; drop it when the OS is under
        // memory pressure. It is reloaded lazily on the next chat.
        if (level >= ComponentCallbacks2.TRIM_MEMORY_UI_HIDDEN) {
            PiSynapseBridge b = PiSynapseBridge.getInstance();
            if (b != null) {
                try {
                    b.llmReleaseNoCall();
                } catch (Exception e) {
                    // ignore
                }
            }
        }
    }
}