from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI

# 1. 아티클 로드
loader = TextLoader("article.txt", encoding="utf-8")
documents = loader.load()

# 2. 텍스트 분할
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
docs = text_splitter.split_documents(documents)

# 3. 임베딩 및 벡터 스토어 생성
embeddings = OpenAIEmbeddings()
vector_store = FAISS.from_documents(docs, embeddings)

# 4. 질의응답 체인 구성
qa_chain = RetrievalQA.from_chain_type(
    llm=OpenAI(), 
    chain_type="stuff", 
    retriever=vector_store.as_retriever()
)

# 5. 사용자 질의에 따른 응답 생성
query = "이 아티클의 주요 내용을 설명해줘."
result = qa_chain.run(query)
print(result)