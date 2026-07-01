import { Router, Route } from "@solidjs/router";
import { CorporaProvider } from "@/corpora/CorporaProvider";
import { ConversationStoreProvider } from "@/conversations/ConversationStoreProvider";
import { RootLayout } from "@/layout/RootLayout";
import { LandingPage } from "@/corpora/LandingPage";
import { CorpusChatPage } from "@/corpora/CorpusChatPage";

const App = () => {
  return (
    <CorporaProvider>
      <ConversationStoreProvider defaultCorpusId="315e41aa-8657-46c0-ac4b-ea4355babf0a">
        <Router root={RootLayout}>
          <Route path="/" component={LandingPage} />
          <Route path="/corpora/:slug" component={CorpusChatPage} />
        </Router>
      </ConversationStoreProvider>
    </CorporaProvider>
  );
};

export default App;
